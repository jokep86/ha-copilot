"""
Alert management — Phase 5.
/alerts         — show recent alerts from alert_log
/alerts clear   — acknowledge all alerts (future)
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from telegram.constants import ParseMode

from app.bot.formatters import bold, code, escape_md
from app.core.module_base import ModuleBase
from app.observability.logger import get_logger

if TYPE_CHECKING:
    from app.bot.handler import CommandContext
    from app.core.module_registry import AppContext

logger = get_logger(__name__)

_SEVERITY_ICON = {"critical": "🚨", "warning": "⚠️", "info": "ℹ️"}


class AlertsModule(ModuleBase):
    name = "alerts"
    description = "Alert history and management"
    commands: list[str] = ["alerts"]

    async def setup(self, app: "AppContext") -> None:
        self._app = app

    async def teardown(self) -> None:
        pass

    async def handle_command(
        self, cmd: str, args: list[str], context: "CommandContext"
    ) -> None:
        engine = self._app.extra.get("alert_engine")
        if not engine:
            await self._reply(context, "Alert engine not available\\.")
            return

        sub = args[0].lower() if args else "list"
        limit = 20

        if sub == "list" or sub.isdigit():
            if sub.isdigit():
                limit = int(sub)
            await self._cmd_list(engine, limit, context)
        else:
            await self._reply(
                context, "Usage: `/alerts` or `/alerts 50` \\(show last N\\)"
            )

    async def _cmd_list(self, engine, limit: int, context: "CommandContext") -> None:
        recent = await engine.get_recent(limit)

        if not recent:
            await self._reply(context, "✅ No alerts recorded\\.")
            return

        lines = [bold(f"Recent Alerts \\({len(recent)}\\)"), ""]
        for a in recent:
            icon = _SEVERITY_ICON.get(a["severity"], "🔔")
            ts = a["timestamp"][:16].replace("T", " ")
            desc = a["description"]
            lines.append(
                f"{icon} {escape_md(desc)}\n"
                f"   {code(escape_md(ts))}"
            )
            if a["auto_fix_attempted"] and a["auto_fix_action"]:
                result = a.get("auto_fix_result", "")
                lines.append(f"   ✅ Fixed: {escape_md(a['auto_fix_action'])}")

        await context.update.message.reply_text(
            "\n".join(lines), parse_mode=ParseMode.MARKDOWN_V2
        )

    async def _reply(self, context: "CommandContext", text: str) -> None:
        await context.update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN_V2)
