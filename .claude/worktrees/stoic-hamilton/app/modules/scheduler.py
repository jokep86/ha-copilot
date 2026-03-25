"""
Scheduled commands management — Phase 4.

Scheduled automations are created by the AI engine with the tag ha_copilot_scheduled
in their description field.

/schedule list   — list pending ha_copilot_scheduled automations
/schedule cancel <id_or_alias> — delete the scheduled automation
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from telegram.constants import ParseMode

from app.bot.formatters import bold, code, error_msg, escape_md, success_msg
from app.core.module_base import ModuleBase
from app.observability.logger import get_logger

if TYPE_CHECKING:
    from app.bot.handler import CommandContext
    from app.core.module_registry import AppContext

logger = get_logger(__name__)

_TAG = "ha_copilot_scheduled"


class SchedulerModule(ModuleBase):
    name = "scheduler"
    description = "NL scheduled commands via HA automations"
    commands: list[str] = ["schedule"]

    async def setup(self, app: "AppContext") -> None:
        self._app = app
        self._ha = app.ha_client

    async def teardown(self) -> None:
        pass

    async def handle_command(
        self, cmd: str, args: list[str], context: "CommandContext"
    ) -> None:
        sub = args[0].lower() if args else "list"

        if sub == "list":
            await self._cmd_list(context)
        elif sub == "cancel":
            query = " ".join(args[1:]) if len(args) > 1 else ""
            await self._cmd_cancel(query, context)
        else:
            await self._reply(
                context,
                "Usage:\n`/schedule list`\n`/schedule cancel \\<id\\_or\\_alias\\>`",
            )

    # ------------------------------------------------------------------ #

    async def _cmd_list(self, context: "CommandContext") -> None:
        try:
            autos = await self._ha.get_automations()
        except Exception as exc:
            await self._reply(context, error_msg(f"Cannot get automations: {exc}"))
            return

        scheduled = [
            a for a in autos
            if _TAG in a.get("description", "")
        ]

        if not scheduled:
            await self._reply(context, "No pending scheduled commands\\.")
            return

        lines = [bold("Scheduled Commands"), ""]
        for a in scheduled:
            alias = a.get("alias", a.get("id", "?"))
            aid = a.get("id", "?")
            # Try to extract trigger time from description
            desc = a.get("description", "")
            trigger_info = ""
            if a.get("trigger"):
                t = a["trigger"][0] if isinstance(a["trigger"], list) else a["trigger"]
                at = t.get("at", t.get("platform", ""))
                if at:
                    trigger_info = f" → {escape_md(str(at))}"
            lines.append(f"⏰ {escape_md(alias)}{trigger_info}\n  {code(aid)}")

        lines.append(f"\n_{len(scheduled)} pending_")
        await context.update.message.reply_text(
            "\n".join(lines), parse_mode=ParseMode.MARKDOWN_V2
        )

    async def _cmd_cancel(self, query: str, context: "CommandContext") -> None:
        if not query:
            await self._reply(context, "Usage: /schedule cancel \\<id\\_or\\_alias\\>")
            return

        try:
            autos = await self._ha.get_automations()
        except Exception as exc:
            await self._reply(context, error_msg(f"Cannot get automations: {exc}"))
            return

        scheduled = [a for a in autos if _TAG in a.get("description", "")]
        q = query.lower()
        found = None
        for a in scheduled:
            if a.get("id", "").lower() == q or q in a.get("alias", "").lower():
                found = a
                break

        if not found:
            await self._reply(
                context,
                escape_md(f"No scheduled command matching '{query}'."),
            )
            return

        alias = found.get("alias", found.get("id", "?"))
        try:
            await self._ha.delete_automation(found["id"])
            await self._reply(context, success_msg(f"Scheduled command '{alias}' cancelled."))
            logger.info("scheduled_cancelled", alias=alias, user_id=context.user_id)
        except Exception as exc:
            await self._reply(context, error_msg(f"Cancel failed: {exc}"))

    async def _reply(self, context: "CommandContext", text: str) -> None:
        await context.update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN_V2)
