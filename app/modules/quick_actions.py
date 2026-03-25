"""
User-defined quick action shortcuts — Phase 8.

/quick            — show inline keyboard of configured shortcuts
/quick <name>     — execute a named quick action directly

Quick actions defined in config.yaml:
  quick_actions:
    - name: "Good Morning"
      actions:
        - service: light.turn_on
          target: {entity_id: light.living_room}
        - service: scene.turn_on
          target: {entity_id: scene.morning}
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode

from app.bot.formatters import bold, error_msg, escape_md, success_msg
from app.core.module_base import ModuleBase
from app.observability.logger import get_logger

if TYPE_CHECKING:
    from app.bot.handler import CommandContext
    from app.core.module_registry import AppContext

logger = get_logger(__name__)


class QuickActionsModule(ModuleBase):
    name = "quick_actions"
    description = "User-defined shortcuts"
    commands: list[str] = ["quick"]

    async def setup(self, app: "AppContext") -> None:
        self._app = app
        self._ha = app.ha_client

    async def teardown(self) -> None:
        pass

    async def handle_command(
        self,
        cmd: str,
        args: list[str],
        context: "CommandContext",
    ) -> None:
        actions = self._app.config.quick_actions
        if not actions:
            await self._reply(
                context,
                "No quick actions configured\\.\n"
                "Add them under `quick_actions` in your add\\-on settings\\.",
            )
            return

        if args:
            # Direct execution by name
            name = " ".join(args)
            await self._execute_by_name(name, context)
        else:
            await self._show_keyboard(actions, context)

    # ------------------------------------------------------------------ #

    async def _show_keyboard(self, actions, context: "CommandContext") -> None:
        """Display an inline keyboard with one button per quick action."""
        buttons = []
        row: list[InlineKeyboardButton] = []
        for qa in actions:
            # Use callback_data: "quick:<name>" (truncated to 64 bytes for TG limit)
            data = f"quick:{qa.name}"[:64]
            row.append(InlineKeyboardButton(text=qa.name, callback_data=data))
            if len(row) == 2:
                buttons.append(row)
                row = []
        if row:
            buttons.append(row)

        await context.update.message.reply_text(
            bold("Quick Actions"),
            reply_markup=InlineKeyboardMarkup(buttons),
            parse_mode=ParseMode.MARKDOWN_V2,
        )

    async def _execute_by_name(self, name: str, context: "CommandContext") -> None:
        actions = self._app.config.quick_actions
        target = next(
            (qa for qa in actions if qa.name.lower() == name.lower()), None
        )
        if not target:
            available = ", ".join(escape_md(qa.name) for qa in actions)
            await self._reply(
                context,
                error_msg(f"Quick action '{name}' not found.") + f"\nAvailable: {available}",
            )
            return

        await self._execute_action(target, context)

    async def execute_by_name_from_callback(
        self, name: str, context: "CommandContext"
    ) -> None:
        """Called from inline keyboard callback handler."""
        await self._execute_by_name(name, context)

    async def _execute_action(self, quick_action, context: "CommandContext") -> None:
        """Execute all service calls for a quick action."""
        errors = []
        for step in quick_action.actions:
            domain, service = step.service.split(".", 1)
            service_data = dict(step.target) if step.target else {}
            try:
                await self._ha.call_service(domain, service, service_data)
                logger.info(
                    "quick_action_step_ok",
                    action=quick_action.name,
                    service=step.service,
                )
            except Exception as exc:
                errors.append(f"{step.service}: {exc}")
                logger.warning(
                    "quick_action_step_failed",
                    action=quick_action.name,
                    service=step.service,
                    error=str(exc),
                )

        if errors:
            err_list = "\n".join(escape_md(e) for e in errors)
            await self._reply(
                context,
                f"⚠️ {bold(escape_md(quick_action.name))} — partial failure:\n{err_list}",
            )
        else:
            await self._reply(
                context,
                success_msg(f"{quick_action.name} executed ({len(quick_action.actions)} steps)."),
            )

    async def _reply(self, context: "CommandContext", text: str) -> None:
        await context.update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN_V2)
