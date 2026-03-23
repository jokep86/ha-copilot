"""
Telegram ID allowlist enforcement (engineering rule 6).
Enforced at middleware level BEFORE any processing.
ALL unauthorized attempts are logged with source_id, username, timestamp.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from telegram import Update

if TYPE_CHECKING:
    from app.config import AppConfig

from app.observability.logger import get_logger

logger = get_logger(__name__)


class AuthMiddleware:
    """
    Validates every update against the configured allowlist.
    Supports private, group, and both modes (chat_mode).
    For groups: also validates against allowed_group_ids if configured.
    """

    def __init__(self, config: "AppConfig") -> None:
        self.config = config

    def is_authorized(self, update: Update) -> bool:
        """Return True if the update is from an authorized user in an allowed chat."""
        if not update.effective_user:
            logger.warning(
                "auth_no_user",
                update_id=update.update_id,
            )
            return False

        user_id = update.effective_user.id
        username = update.effective_user.username
        chat = update.effective_chat
        chat_id = chat.id if chat else None
        chat_type = chat.type if chat else "unknown"

        is_private = chat_type == "private"
        is_group = chat_type in ("group", "supergroup")

        # Enforce chat_mode
        mode = self.config.chat_mode
        if mode == "private" and not is_private:
            logger.warning(
                "auth_rejected_wrong_chat_mode",
                user_id=user_id,
                username=username,
                chat_id=chat_id,
                chat_type=chat_type,
                required_mode=mode,
            )
            return False

        if mode == "group" and not is_group:
            logger.warning(
                "auth_rejected_wrong_chat_mode",
                user_id=user_id,
                username=username,
                chat_id=chat_id,
                chat_type=chat_type,
                required_mode=mode,
            )
            return False

        # For groups: check group allowlist if configured
        if is_group and self.config.allowed_group_ids:
            if chat_id not in self.config.allowed_group_ids:
                logger.warning(
                    "auth_rejected_group_not_allowed",
                    user_id=user_id,
                    username=username,
                    chat_id=chat_id,
                )
                return False

        # Check user allowlist
        if user_id not in self.config.allowed_telegram_ids:
            logger.warning(
                "auth_rejected_user_not_allowed",
                user_id=user_id,
                username=username,
                chat_id=chat_id,
                update_id=update.update_id,
            )
            return False

        return True

    async def check(self, update: Update) -> bool:
        """Async wrapper — may be extended for DB-backed checks in future phases."""
        return self.is_authorized(update)
