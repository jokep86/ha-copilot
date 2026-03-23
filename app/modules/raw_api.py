"""
Direct HA API calls for power users — Phase 3.

/raw GET /api/states/light.sala
/raw POST /api/services/light/turn_on {"entity_id": "light.sala"}
/raw SUP GET /supervisor/info
/raw SUP POST /addons/slug/restart

GET requests execute immediately.
POST/PUT/DELETE require confirmation: add "confirm" as first arg after method.
  /raw POST confirm /api/services/light/turn_on {"entity_id": "light.sala"}
"""
from __future__ import annotations

import json
from typing import TYPE_CHECKING

import aiohttp
import orjson
from telegram.constants import ParseMode

from app.bot.formatters import bold, code, error_msg, escape_md
from app.core.module_base import ModuleBase
from app.observability.logger import get_logger

if TYPE_CHECKING:
    from app.bot.handler import CommandContext
    from app.core.module_registry import AppContext

logger = get_logger(__name__)

_READONLY_METHODS = {"GET", "HEAD"}
_HA_BASE = "http://supervisor/core/api"
_SUP_BASE = "http://supervisor"

MAX_RESPONSE_CHARS = 3000


class RawApiModule(ModuleBase):
    name = "raw_api"
    description = "Direct HA API calls for power users"
    commands: list[str] = ["raw"]

    async def setup(self, app: "AppContext") -> None:
        self._app = app

    async def teardown(self) -> None:
        pass

    async def handle_command(
        self, cmd: str, args: list[str], context: "CommandContext"
    ) -> None:
        if not args:
            await self._reply(
                context,
                bold("Raw API") + "\n"
                "Usage:\n"
                "`/raw GET /api/states/sensor\\.temp`\n"
                "`/raw POST /api/services/light/turn_on \\{\"entity_id\":\"light\\.sala\"\\}`\n"
                "`/raw SUP GET /supervisor/info`\n"
                "`/raw POST confirm /api/...` — skip confirmation prompt",
            )
            return

        # Determine if this is a Supervisor call
        supervisor = False
        if args[0].upper() == "SUP":
            supervisor = True
            args = args[1:]

        if not args:
            await self._reply(context, error_msg("Missing HTTP method."))
            return

        method = args[0].upper()
        if method not in ("GET", "POST", "PUT", "DELETE", "PATCH"):
            await self._reply(context, error_msg(f"Unknown method: {method}"))
            return

        # Confirmation check for mutating methods
        confirmed = False
        remaining = args[1:]
        if remaining and remaining[0] == "confirm":
            confirmed = True
            remaining = remaining[1:]

        if not remaining:
            await self._reply(context, error_msg("Missing path."))
            return

        path = remaining[0]
        body_str = " ".join(remaining[1:]) if len(remaining) > 1 else None

        # Parse optional JSON body
        body: dict | None = None
        if body_str:
            try:
                body = json.loads(body_str)
            except json.JSONDecodeError as exc:
                await self._reply(context, error_msg(f"Invalid JSON body: {exc}"))
                return

        # Require confirmation for mutating calls
        if method not in _READONLY_METHODS and not confirmed:
            sup_prefix = "SUP " if supervisor else ""
            body_hint = f" {escape_md(body_str)}" if body_str else ""
            await self._reply(
                context,
                f"⚠️ {bold(method)} {code(path)}{escape_md(body_hint[:80])}\n"
                f"Send with `confirm` to execute:\n"
                f"`/raw {sup_prefix}{method} confirm {escape_md(path)}{escape_md(body_hint[:80])}`",
            )
            return

        await self._execute(method, path, body, supervisor, context)

    async def _execute(
        self,
        method: str,
        path: str,
        body: dict | None,
        supervisor: bool,
        context: "CommandContext",
    ) -> None:
        import os

        token = os.environ.get("SUPERVISOR_TOKEN", "")
        base = _SUP_BASE if supervisor else _HA_BASE
        url = base + path

        status_code = None
        response_text = ""

        try:
            async with aiohttp.ClientSession(
                headers={"Authorization": f"Bearer {token}"},
                timeout=aiohttp.ClientTimeout(total=30),
            ) as session:
                async with session.request(method, url, json=body) as resp:
                    status_code = resp.status
                    response_text = await resp.text()
        except Exception as exc:
            await self._reply(context, error_msg(f"Request failed: {exc}"))
            return

        # Try to pretty-print JSON
        try:
            parsed = orjson.loads(response_text)
            pretty = json.dumps(parsed, indent=2, ensure_ascii=False)
        except Exception:
            pretty = response_text

        if len(pretty) > MAX_RESPONSE_CHARS:
            pretty = pretty[:MAX_RESPONSE_CHARS] + "\n…(truncated)"

        icon = "✅" if status_code and status_code < 400 else "🔴"
        header = f"{icon} {bold(method)} {code(path)} → {code(str(status_code))}"

        await context.update.message.reply_text(
            f"{header}\n```json\n{pretty}\n```",
            parse_mode=ParseMode.MARKDOWN_V2,
        )

        # Log to raw_api_log
        try:
            await self._app.db.conn.execute(
                """
                INSERT INTO raw_api_log (user_id, method, path, body, status_code, response_summary)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    context.user_id,
                    method,
                    path,
                    json.dumps(body) if body else None,
                    status_code,
                    pretty[:200],
                ),
            )
            await self._app.db.conn.commit()
        except Exception as exc:
            logger.error("raw_api_log_failed", error=str(exc))

        logger.info(
            "raw_api_call",
            user_id=context.user_id,
            method=method,
            path=path,
            status=status_code,
        )

    async def _reply(self, context: "CommandContext", text: str) -> None:
        await context.update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN_V2)
