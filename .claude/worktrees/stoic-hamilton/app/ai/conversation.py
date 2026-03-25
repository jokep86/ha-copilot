"""
Conversation memory — stores recent messages per user in SQLite.
Configurable TTL and max message count (see AppConfig).
Enables contextual NL: "bajala al 30%" after "prendé la sala".
"""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.database import Database

from app.observability.logger import get_logger

logger = get_logger(__name__)

_INSERT = """
    INSERT INTO conversation_context (user_id, role, content, trace_id)
    VALUES (?, ?, ?, ?)
"""

_SELECT = """
    SELECT role, content
    FROM conversation_context
    WHERE user_id = ?
      AND timestamp >= datetime('now', ?)
    ORDER BY timestamp ASC
    LIMIT ?
"""

_PURGE = """
    DELETE FROM conversation_context
    WHERE user_id = ?
      AND timestamp < datetime('now', ?)
"""


class ConversationMemory:
    def __init__(
        self,
        db: "Database",
        enabled: bool = True,
        ttl_minutes: int = 30,
        max_messages: int = 10,
    ) -> None:
        self.db = db
        self.enabled = enabled
        self.ttl_minutes = ttl_minutes
        self.max_messages = max_messages

    async def add(
        self,
        user_id: int,
        role: str,
        content: str,
        trace_id: str = "",
    ) -> None:
        """Store a message. role: 'user' or 'assistant'."""
        if not self.enabled:
            return
        await self.db.conn.execute(_INSERT, (user_id, role, content, trace_id))
        await self.db.conn.commit()

    async def get_history(self, user_id: int) -> list[dict[str, str]]:
        """Return [{role, content}, ...] for the last N messages within TTL."""
        if not self.enabled:
            return []
        cursor = await self.db.conn.execute(
            _SELECT,
            (user_id, f"-{self.ttl_minutes} minutes", self.max_messages),
        )
        rows = await cursor.fetchall()
        return [{"role": row[0], "content": row[1]} for row in rows]

    async def purge_user(self, user_id: int) -> None:
        """Remove all context for a user older than TTL."""
        await self.db.conn.execute(
            _PURGE, (user_id, f"-{self.ttl_minutes} minutes")
        )
        await self.db.conn.commit()
