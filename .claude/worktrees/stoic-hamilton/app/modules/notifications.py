"""
Notification management — Phase 5.
/notify on|off  — enable or disable proactive notifications for the user
/subs           — list active event subscription types
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from telegram.constants import ParseMode

from app.bot.formatters import bold, code, escape_md, success_msg
from app.core.module_base import ModuleBase
from app.observability.logger import get_logger

if TYPE_CHECKING:
    from app.bot.handler import CommandContext
    from app.core.module_registry import AppContext

logger = get_logger(__name__)


class NotificationsModule(ModuleBase):
    name = "notifications"
    description = "Proactive notification management"
    commands: list[str] = ["notify", "subs"]

    async def setup(self, app: "AppContext") -> None:
        self._app = app

    async def teardown(self) -> None:
        pass

    async def handle_command(
        self, cmd: str, args: list[str], context: "CommandContext"
    ) -> None:
        if cmd == "notify":
            await self._cmd_notify(args, context)
        else:
            await self._cmd_subs(context)

    # ------------------------------------------------------------------ #

    async def _cmd_notify(self, args: list[str], context: "CommandContext") -> None:
        listener = self._app.extra.get("event_listener")
        if not listener:
            await self._reply(context, "Event listener not available\\.")
            return

        if not args:
            state = "on" if listener.is_enabled(context.user_id) else "off"
            await self._reply(
                context,
                f"Notifications are currently {bold(escape_md(state))}\\.\n"
                f"Send `/notify on` or `/notify off` to change\\.",
            )
            return

        action = args[0].lower()
        if action == "on":
            listener.enable(context.user_id)
            await self._reply(context, success_msg("Proactive notifications enabled."))
        elif action == "off":
            listener.disable(context.user_id)
            await self._reply(context, "🔕 Proactive notifications disabled\\.")
        else:
            await self._reply(context, "Usage: `/notify on` or `/notify off`")

    async def _cmd_subs(self, context: "CommandContext") -> None:
        listener = self._app.extra.get("event_listener")
        if not listener:
            await self._reply(context, "Event listener not available\\.")
            return

        types = listener.get_subscribed_types()
        if not types:
            await self._reply(context, "No active event subscriptions\\.")
            return

        enabled = listener.is_enabled(context.user_id)
        status = "🟢 enabled" if enabled else "🔴 disabled"
        lines = [
            bold("Event Subscriptions"),
            f"Your notifications: {escape_md(status)}",
            "",
        ]
        for t in types:
            lines.append(f"• {code(t)}")

        await context.update.message.reply_text(
            "\n".join(lines), parse_mode=ParseMode.MARKDOWN_V2
        )

    async def _reply(self, context: "CommandContext", text: str) -> None:
        await context.update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN_V2)
