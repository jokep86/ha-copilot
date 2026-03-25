"""
Inline keyboard callback handlers.
Routes: pagination, domain selection, toggle, confirm/cancel actions.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from app.bot.formatters import escape_md, success_msg, warning_msg
from app.bot.pagination import parse_page_callback
from app.observability.logger import get_logger

if TYPE_CHECKING:
    from app.ai.mapper import PendingActions
    from app.ha.client import HAClient

logger = get_logger(__name__)

# Injected at startup by main.py via set_dependencies()
_pending_actions: "PendingActions | None" = None
_ha_client: "HAClient | None" = None


def set_dependencies(pending: "PendingActions", ha: "HAClient") -> None:
    """Called from main.py after all objects are wired."""
    global _pending_actions, _ha_client
    _pending_actions = pending
    _ha_client = ha


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

    # --- Pagination ---
    page = parse_page_callback(data)
    if page is not None:
        if context.user_data is not None:
            context.user_data["current_page"] = page
        return

    # --- Confirm action ---
    if data.startswith("confirm:"):
        action_id = data.split(":", 1)[1]
        if _pending_actions:
            ok = await _pending_actions.confirm(action_id)
            if ok:
                await query.edit_message_text(
                    "✅ Done\\.", parse_mode=ParseMode.MARKDOWN_V2
                )
            else:
                await query.edit_message_text(
                    "🔴 Action expired or failed\\.", parse_mode=ParseMode.MARKDOWN_V2
                )
        return

    # --- Cancel action ---
    if data.startswith("cancel:"):
        action_id = data.split(":", 1)[1]
        if _pending_actions:
            await _pending_actions.cancel(action_id)
        await query.edit_message_text(
            "❌ Cancelled\\.", parse_mode=ParseMode.MARKDOWN_V2
        )
        return

    # --- Domain button (from /devices summary) ---
    if data.startswith("domain:"):
        domain = data.split(":", 1)[1]
        # Re-invoke /devices <domain> in user context
        # We can't easily call the module here, so we update the message with a hint
        await query.edit_message_text(
            f"Send `/devices {escape_md(domain)}` to list {escape_md(domain)} entities\\.",
            parse_mode=ParseMode.MARKDOWN_V2,
        )
        return

    # --- Toggle button (from /devices <domain>) ---
    if data.startswith("toggle:"):
        entity_id = data.split(":", 1)[1]
        if _ha_client:
            try:
                state_data = await _ha_client.get_state(entity_id)
                domain = entity_id.split(".")[0]
                current = state_data.get("state", "off")
                service = "turn_off" if current == "on" else "turn_on"
                await _ha_client.call_service(domain, service, {"entity_id": entity_id})
                new_state = "off" if current == "on" else "on"
                fname = state_data.get("attributes", {}).get("friendly_name", entity_id)
                icon = "🔴" if new_state == "off" else "🟢"
                await query.answer(f"{icon} {fname} → {new_state}", show_alert=False)
                # Update button label in-place
                await query.edit_message_reply_markup(reply_markup=None)
            except Exception as exc:
                logger.error("toggle_callback_failed", entity_id=entity_id, error=str(exc))
                await query.answer(f"Error: {exc}", show_alert=True)
        return

    logger.warning("unhandled_callback", data=data)
