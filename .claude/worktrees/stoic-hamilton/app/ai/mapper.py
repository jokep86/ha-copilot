"""
AI response → HA action mapper.
Takes an AIResponse, routes each AIAction to the appropriate HA client call,
applies confirmation levels, handles undo logging.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

from app.observability.logger import get_logger
from app.schemas.ai_action import ActionType, AIResponse

if TYPE_CHECKING:
    from app.bot.handler import CommandContext
    from app.config import AppConfig
    from app.ha.client import HAClient
    from app.ha.discovery import EntityDiscovery
    from app.undo.manager import UndoManager

logger = get_logger(__name__)

# Actions that require single_click confirmation
_SINGLE_CLICK_ACTIONS = {ActionType.CALL_SERVICE}
# Actions that need double confirmation (CRUD)
_DOUBLE_CONFIRM_ACTIONS = {
    ActionType.CREATE_AUTOMATION,
    ActionType.EDIT_AUTOMATION,
    ActionType.CREATE_SCENE,
}
# Actions that need password
_PASSWORD_ACTIONS = {
    ActionType.DELETE_AUTOMATION,
    ActionType.DELETE_SCENE,
}


class AIActionMapper:
    """Executes AIResponse actions against the HA API, respecting confirmation levels."""

    def __init__(
        self,
        ha_client: "HAClient",
        discovery: "EntityDiscovery",
        config: "AppConfig",
        undo_manager: "UndoManager",
        pending_actions: "PendingActions",
    ) -> None:
        self.ha = ha_client
        self.discovery = discovery
        self.config = config
        self.undo = undo_manager
        self.pending = pending_actions

    async def execute(
        self,
        response: AIResponse,
        context: "CommandContext",
    ) -> None:
        """Route all actions in the response."""
        if not response.actions:
            await self._reply(context, "I couldn't understand that. Try rephrasing.")
            return

        for action in response.actions:
            await self._dispatch(action, response.trace_id, context)

    async def _dispatch(
        self,
        action: Any,
        trace_id: str,
        context: "CommandContext",
    ) -> None:
        from app.bot.formatters import escape_md

        atype = action.action_type

        # --- Immediate read-only actions ---
        if atype == ActionType.GET_STATE:
            await self._do_get_state(action, context)
            return

        if atype == ActionType.LIST_ENTITIES:
            await self._do_list_entities(action, context)
            return

        if atype == ActionType.SYSTEM_INFO:
            await self._reply(context, "Use /sys for system info.")
            return

        if atype == ActionType.CLARIFICATION_NEEDED:
            msg = action.message or "Could you be more specific?"
            await self._reply(context, escape_md(msg))
            return

        if atype == ActionType.UNKNOWN:
            await self._reply(
                context,
                "I couldn't understand that command\\. Try rephrasing, or use /help\\.",
            )
            return

        # --- Scene activation (single click) ---
        if atype == ActionType.ACTIVATE_SCENE:
            await self._with_confirmation(
                action, trace_id, context,
                confirm_level="single_click",
                preview=f"Activate scene: {action.entity_id or '?'}",
                executor=self._do_activate_scene,
            )
            return

        # --- Toggle/trigger automation ---
        if atype in (ActionType.TOGGLE_AUTOMATION, ActionType.TRIGGER_AUTOMATION):
            await self._with_confirmation(
                action, trace_id, context,
                confirm_level="single_click",
                preview=f"{atype.value.replace('_', ' ').title()}: {action.entity_id or '?'}",
                executor=self._do_automation_op,
            )
            return

        # --- Service call (most common NL action) ---
        if atype == ActionType.CALL_SERVICE:
            entities = action.entity_ids or ([action.entity_id] if action.entity_id else [])
            preview_line = (
                f"{action.domain}.{action.service} → "
                f"{', '.join(entities) or 'all'}"
            )
            confirm_level = (
                "double_confirm" if len(entities) > 3 else "single_click"
            )
            await self._with_confirmation(
                action, trace_id, context,
                confirm_level=confirm_level,
                preview=preview_line,
                executor=self._do_call_service,
            )
            return

        # --- CRUD (Phase 4) stub ---
        if atype in _DOUBLE_CONFIRM_ACTIONS:
            await self._reply(
                context,
                f"Automation/scene CRUD coming in Phase 4\\. Use /help\\.",
            )
            return

        await self._reply(context, f"Action `{atype.value}` not yet implemented\\.")

    # ------------------------------------------------------------------ #
    # Confirmation flow
    # ------------------------------------------------------------------ #

    async def _with_confirmation(
        self,
        action: Any,
        trace_id: str,
        context: "CommandContext",
        confirm_level: str,
        preview: str,
        executor: Any,
    ) -> None:
        """
        Wrap an action with the appropriate confirmation level.
        none → execute immediately.
        single_click → show ✅/❌ inline keyboard.
        double_confirm / password → not yet implemented for NL (Phase 4).
        """
        if context.chat_id is None:
            return

        configured_none = self.config.confirmation_levels.none
        if action.action_type.value in configured_none:
            await executor(action, context)
            return

        if confirm_level == "single_click":
            action_id = await self.pending.store(
                action=action,
                trace_id=trace_id,
                user_id=context.user_id,
                executor=executor,
                context=context,
            )
            from telegram import InlineKeyboardButton, InlineKeyboardMarkup
            keyboard = InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("✅ Confirm", callback_data=f"confirm:{action_id}"),
                    InlineKeyboardButton("❌ Cancel", callback_data=f"cancel:{action_id}"),
                ]
            ])
            from app.bot.formatters import escape_md
            from telegram.constants import ParseMode
            await context.update.message.reply_text(
                f"*Confirm action:*\n{escape_md(preview)}",
                parse_mode=ParseMode.MARKDOWN_V2,
                reply_markup=keyboard,
            )
            return

        # For double_confirm / password — execute directly for now (Phase 4 will add flow)
        await executor(action, context)

    # ------------------------------------------------------------------ #
    # Executors
    # ------------------------------------------------------------------ #

    async def _do_get_state(self, action: Any, context: "CommandContext") -> None:
        from app.bot.formatters import entity_state_msg
        from telegram.constants import ParseMode

        entity_id = action.entity_id
        if not entity_id:
            await self._reply(context, "Which entity? Please specify an entity ID.")
            return
        try:
            state = await self.ha.get_state(entity_id)
            text = entity_state_msg(
                state["entity_id"],
                state["state"],
                state.get("attributes", {}),
            )
            await context.update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN_V2)
        except Exception as exc:
            await self._reply(context, f"Could not get state: {exc}")

    async def _do_list_entities(self, action: Any, context: "CommandContext") -> None:
        from app.bot.formatters import escape_md
        from telegram.constants import ParseMode

        domain = action.domain
        if domain:
            entities = await self.discovery.get_entities_by_domain(domain)
        else:
            entities = await self.discovery.get_all_states()

        if not entities:
            await self._reply(context, f"No entities found for domain '{domain}'.")
            return

        lines = [f"*{escape_md(domain or 'All')} entities:*"]
        for e in entities[:20]:
            eid = e.get("entity_id", "")
            state = e.get("state", "")
            fname = e.get("attributes", {}).get("friendly_name", eid)
            lines.append(f"• {escape_md(fname)} — {escape_md(state)}")
        if len(entities) > 20:
            lines.append(f"_… and {len(entities) - 20} more\\. Use /entities {domain or ''}_")

        await context.update.message.reply_text(
            "\n".join(lines),
            parse_mode=ParseMode.MARKDOWN_V2,
        )

    async def _do_call_service(self, action: Any, context: "CommandContext") -> None:
        from app.bot.formatters import escape_md, success_msg
        from telegram.constants import ParseMode

        domain = action.domain
        service = action.service
        entities = action.entity_ids or ([action.entity_id] if action.entity_id else [])
        service_data: dict = dict(action.service_data)

        if entities:
            service_data["entity_id"] = entities if len(entities) > 1 else entities[0]

        # Save undo state (before executing)
        for eid in (entities or []):
            try:
                prev_state = await self.ha.get_state(eid)
                await self.undo.save(
                    user_id=context.user_id,
                    action_type=f"{domain}.{service}",
                    entity_id=eid,
                    previous_state=prev_state,
                )
            except Exception:
                pass  # best-effort undo

        try:
            await self.ha.call_service(domain, service, service_data)
            entity_str = ", ".join(entities) if entities else f"{domain} entities"
            await context.update.message.reply_text(
                success_msg(f"{domain}.{service} → {entity_str}"),
                parse_mode=ParseMode.MARKDOWN_V2,
            )
        except Exception as exc:
            await self._reply(context, f"Service call failed: {exc}")

    async def _do_activate_scene(self, action: Any, context: "CommandContext") -> None:
        try:
            await self.ha.call_service("scene", "turn_on", {"entity_id": action.entity_id})
            from app.bot.formatters import success_msg
            from telegram.constants import ParseMode
            await context.update.message.reply_text(
                success_msg(f"Scene activated: {action.entity_id}"),
                parse_mode=ParseMode.MARKDOWN_V2,
            )
        except Exception as exc:
            await self._reply(context, f"Scene activation failed: {exc}")

    async def _do_automation_op(self, action: Any, context: "CommandContext") -> None:
        atype = action.action_type
        eid = action.entity_id
        try:
            if atype == ActionType.TOGGLE_AUTOMATION:
                # Toggle: check current state first
                state = await self.ha.get_state(eid)
                if state.get("state") == "on":
                    await self.ha.call_service("automation", "turn_off", {"entity_id": eid})
                    verb = "disabled"
                else:
                    await self.ha.call_service("automation", "turn_on", {"entity_id": eid})
                    verb = "enabled"
            else:  # trigger
                await self.ha.call_service("automation", "trigger", {"entity_id": eid})
                verb = "triggered"

            from app.bot.formatters import success_msg
            from telegram.constants import ParseMode
            await context.update.message.reply_text(
                success_msg(f"Automation {verb}: {eid}"),
                parse_mode=ParseMode.MARKDOWN_V2,
            )
        except Exception as exc:
            await self._reply(context, f"Automation operation failed: {exc}")

    async def _reply(self, context: "CommandContext", text: str) -> None:
        from telegram.constants import ParseMode
        await context.update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN_V2)


class PendingActions:
    """
    In-memory store for actions awaiting user confirmation.
    TTL: 60 seconds (confirmation must happen within this window).
    """

    TTL_SECONDS = 60

    def __init__(self) -> None:
        import time
        self._actions: dict[str, dict] = {}
        self._time = time

    async def store(
        self,
        action: Any,
        trace_id: str,
        user_id: int,
        executor: Any,
        context: "CommandContext",
    ) -> str:
        import uuid
        action_id = str(uuid.uuid4())[:8]
        self._actions[action_id] = {
            "action": action,
            "trace_id": trace_id,
            "user_id": user_id,
            "executor": executor,
            "context": context,
            "ts": self._time.monotonic(),
        }
        return action_id

    async def pop(self, action_id: str) -> dict | None:
        import time
        entry = self._actions.pop(action_id, None)
        if not entry:
            return None
        if time.monotonic() - entry["ts"] > self.TTL_SECONDS:
            logger.warning("pending_action_expired", action_id=action_id)
            return None
        return entry

    async def confirm(self, action_id: str) -> bool:
        entry = await self.pop(action_id)
        if not entry:
            return False
        try:
            await entry["executor"](entry["action"], entry["context"])
            return True
        except Exception as exc:
            logger.error("pending_action_execute_failed", action_id=action_id, error=str(exc))
            return False

    async def cancel(self, action_id: str) -> bool:
        entry = self._actions.pop(action_id, None)
        return entry is not None
