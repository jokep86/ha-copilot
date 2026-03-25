"""
Proactive notification sender.
Sends Telegram messages to configured targets and logs to notification_log.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any, Callable, Coroutine

from app.observability.logger import get_logger

if TYPE_CHECKING:
    from app.config import AppConfig
    from app.database import Database

logger = get_logger(__name__)

BotSendFn = Callable[[int, str], Coroutine[Any, Any, None]]

_INSERT = """
    INSERT INTO notification_log (event_type, entity_id, message, chat_id, was_auto_fix, fix_action, fix_result)
    VALUES (?, ?, ?, ?, ?, ?, ?)
"""


class Notifier:
    def __init__(self, config: "AppConfig", db: "Database") -> None:
        self._config = config
        self._db = db
        self._bot_send: BotSendFn | None = None

    def set_bot_send(self, fn: BotSendFn) -> None:
        """Injected after bot is set up (to avoid circular init order)."""
        self._bot_send = fn

    async def send(
        self,
        event_type: str,
        entity_id: str | None,
        message: str,
        was_auto_fix: bool = False,
        fix_action: str | None = None,
        fix_result: str | None = None,
    ) -> None:
        """Send notification to all configured targets and log it."""
        if not self._bot_send:
            logger.warning("notifier_bot_send_not_set")
            return

        target_ids = self._resolve_targets()
        for chat_id in target_ids:
            try:
                await self._bot_send(chat_id, message)
            except Exception as exc:
                logger.error(
                    "notifier_send_failed",
                    chat_id=chat_id,
                    error=str(exc),
                )

            # Log each send
            try:
                await self._db.conn.execute(
                    _INSERT,
                    (event_type, entity_id, message, chat_id,
                     was_auto_fix, fix_action, fix_result),
                )
                await self._db.conn.commit()
            except Exception as exc:
                logger.error("notifier_log_failed", error=str(exc))

    def _resolve_targets(self) -> list[int]:
        """Return chat IDs to send to based on notification_target config."""
        # For Phase 5: send to all allowed_telegram_ids
        # (group vs private routing deferred until Phase 5+ when group IDs are tracked)
        return list(self._config.allowed_telegram_ids)
