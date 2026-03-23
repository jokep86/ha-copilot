"""
Inline keyboard callback handlers.
"""
from __future__ import annotations

from telegram import Update
from telegram.ext import ContextTypes

from app.bot.pagination import parse_page_callback
from app.observability.logger import get_logger

logger = get_logger(__name__)


async def handle_callback_query(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    """Route all inline keyboard callbacks."""
    query = update.callback_query
    if not query:
        return

    await query.answer()
    data = query.data or ""

    if data == "noop":
        return

    page = parse_page_callback(data)
    if page is not None:
        # Store current page in user_data so the originating handler can re-render.
        # Handlers that support pagination check context.user_data["current_page"].
        if context.user_data is not None:
            context.user_data["current_page"] = page
        logger.debug("pagination_callback", page=page, user_id=query.from_user.id if query.from_user else None)
        return

    logger.warning("unhandled_callback", data=data)
