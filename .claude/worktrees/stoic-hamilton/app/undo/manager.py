"""
Undo system for destructive actions.
Saves previous entity state before every service call.
/undo reverts the most recent action within TTL (default 10 min).
Only the latest action per entity is undoable.
"""
from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.database import Database
    from app.ha.client import HAClient

from app.observability.logger import get_logger

logger = get_logger(__name__)

DEFAULT_TTL = 600  # 10 minutes

_INSERT = """
    INSERT INTO undo_log (user_id, action_type, entity_id, previous_state, ttl_seconds)
    VALUES (?, ?, ?, ?, ?)
"""

_GET_LATEST = """
    SELECT id, action_type, entity_id, previous_state
    FROM undo_log
    WHERE user_id = ?
      AND used = 0
      AND datetime(timestamp, '+' || ttl_seconds || ' seconds') > datetime('now')
    ORDER BY timestamp DESC
    LIMIT 1
"""

_MARK_USED = "UPDATE undo_log SET used = 1 WHERE id = ?"


class UndoManager:
    def __init__(
        self,
        db: "Database",
        ha_client: "HAClient",
        ttl_seconds: int = DEFAULT_TTL,
    ) -> None:
        self.db = db
        self.ha = ha_client
        self.ttl = ttl_seconds

    async def save(
        self,
        user_id: int,
        action_type: str,
        entity_id: str,
        previous_state: dict[str, Any],
    ) -> None:
        """Save the current entity state before a mutation."""
        await self.db.conn.execute(
            _INSERT,
            (user_id, action_type, entity_id, json.dumps(previous_state), self.ttl),
        )
        await self.db.conn.commit()
        logger.debug("undo_saved", user_id=user_id, entity_id=entity_id)

    async def undo_last(self, user_id: int) -> str | None:
        """
        Revert the most recent undoable action for this user.
        Returns a human-readable result message, or None if nothing to undo.
        """
        cursor = await self.db.conn.execute(_GET_LATEST, (user_id,))
        row = await cursor.fetchone()
        if not row:
            return None

        row_id, action_type, entity_id, prev_state_json = row
        prev_state = json.loads(prev_state_json)

        domain = entity_id.split(".")[0]
        prev = prev_state.get("state", "unknown")

        try:
            # Re-apply previous state
            if prev in ("on", "off"):
                service = "turn_on" if prev == "on" else "turn_off"
                await self.ha.call_service(domain, service, {"entity_id": entity_id})
            else:
                # For numeric states (brightness, temperature, etc.)
                attrs = prev_state.get("attributes", {})
                service_data: dict[str, Any] = {"entity_id": entity_id}
                if "brightness" in attrs:
                    service_data["brightness"] = attrs["brightness"]
                if "temperature" in attrs and domain == "climate":
                    service_data["temperature"] = attrs["temperature"]
                await self.ha.call_service(domain, "set_value", service_data)

            # Mark as used
            await self.db.conn.execute(_MARK_USED, (row_id,))
            await self.db.conn.commit()

            logger.info(
                "undo_applied",
                user_id=user_id,
                entity_id=entity_id,
                prev_state=prev,
            )
            return f"Reverted {entity_id} → {prev}"

        except Exception as exc:
            logger.error("undo_failed", entity_id=entity_id, error=str(exc))
            return f"Undo failed for {entity_id}: {exc}"

    async def get_pending(self, user_id: int) -> list[dict]:
        """Return list of undoable actions for this user."""
        cursor = await self.db.conn.execute(
            """
            SELECT action_type, entity_id, timestamp
            FROM undo_log
            WHERE user_id = ?
              AND used = 0
              AND datetime(timestamp, '+' || ttl_seconds || ' seconds') > datetime('now')
            ORDER BY timestamp DESC
            """,
            (user_id,),
        )
        rows = await cursor.fetchall()
        return [
            {"action": r[0], "entity_id": r[1], "timestamp": r[2]} for r in rows
        ]
