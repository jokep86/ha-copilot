"""
AI Decision Audit Log.
Every Claude call is logged: raw prompt + raw response + parsed actions + tokens.
Also tracks daily token usage for budget enforcement.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.database import Database
    from app.schemas.ai_action import AIResponse

from app.observability.logger import get_logger

logger = get_logger(__name__)

_INSERT_AUDIT = """
    INSERT INTO ai_audit_log
        (trace_id, user_id, raw_prompt, raw_response, parsed_actions,
         final_action_taken, prompt_version, model,
         input_tokens, output_tokens, latency_ms, success)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
"""

_UPSERT_TOKENS = """
    INSERT INTO token_usage (date, model, total_input_tokens, total_output_tokens, total_requests)
    VALUES (?, ?, ?, ?, 1)
    ON CONFLICT(date, model) DO UPDATE SET
        total_input_tokens = total_input_tokens + excluded.total_input_tokens,
        total_output_tokens = total_output_tokens + excluded.total_output_tokens,
        total_requests = total_requests + 1
"""

_GET_DAILY_TOKENS = """
    SELECT COALESCE(SUM(total_input_tokens + total_output_tokens), 0)
    FROM token_usage
    WHERE date = ?
"""


class AIAuditLog:
    def __init__(self, db: "Database") -> None:
        self.db = db

    async def log(
        self,
        response: "AIResponse",
        user_id: int,
        raw_prompt: str,
        final_action: str | None = None,
        latency_ms: int | None = None,
        success: bool = True,
    ) -> None:
        """Write one audit row and update daily token counter."""
        parsed_actions = json.dumps(
            [a.model_dump() for a in response.actions], default=str
        )
        await self.db.conn.execute(
            _INSERT_AUDIT,
            (
                response.trace_id,
                user_id,
                raw_prompt,
                response.raw_response,
                parsed_actions,
                final_action,
                response.prompt_version,
                response.model,
                response.input_tokens,
                response.output_tokens,
                latency_ms,
                success,
            ),
        )
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        await self.db.conn.execute(
            _UPSERT_TOKENS,
            (today, response.model, response.input_tokens, response.output_tokens),
        )
        await self.db.conn.commit()
        logger.info(
            "ai_audit_logged",
            trace_id=response.trace_id,
            model=response.model,
            input_tokens=response.input_tokens,
            output_tokens=response.output_tokens,
        )

    async def get_daily_tokens_used(self) -> int:
        """Return total tokens used today (input + output)."""
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        cursor = await self.db.conn.execute(_GET_DAILY_TOKENS, (today,))
        row = await cursor.fetchone()
        return row[0] if row else 0

    async def get_stats(self, days: int = 30) -> dict[str, Any]:
        """Return usage summary for the last N days."""
        cursor = await self.db.conn.execute(
            """
            SELECT date, model,
                   total_input_tokens, total_output_tokens, total_requests
            FROM token_usage
            WHERE date >= date('now', ?)
            ORDER BY date DESC
            """,
            (f"-{days} days",),
        )
        rows = await cursor.fetchall()
        return {
            "days": days,
            "rows": [
                {
                    "date": r[0],
                    "model": r[1],
                    "input_tokens": r[2],
                    "output_tokens": r[3],
                    "requests": r[4],
                }
                for r in rows
            ],
        }
