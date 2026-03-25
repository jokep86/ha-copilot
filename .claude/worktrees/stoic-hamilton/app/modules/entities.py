"""
Entity management module — Phase 2.
/entities [domain] — paginated list of all entities.
/history <entity_id> [hours] — state history (text or chart).
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from telegram.constants import ParseMode

from app.bot.formatters import bold, code, entity_state_msg, error_msg, escape_md
from app.bot.pagination import paginate
from app.core.module_base import ModuleBase
from app.observability.logger import get_logger

if TYPE_CHECKING:
    from app.bot.handler import CommandContext
    from app.core.module_registry import AppContext

logger = get_logger(__name__)


class EntitiesModule(ModuleBase):
    name = "entities"
    description = "Entity listing and history"
    commands: list[str] = ["entities", "history"]

    async def setup(self, app: "AppContext") -> None:
        self._app = app
        self._ha = app.ha_client
        self._discovery = app.extra.get("discovery")

    async def teardown(self) -> None:
        pass

    async def handle_command(
        self, cmd: str, args: list[str], context: "CommandContext"
    ) -> None:
        if cmd == "history":
            await self._cmd_history(args, context)
        else:
            await self._cmd_entities(args, context)

    # ------------------------------------------------------------------ #

    async def _cmd_entities(
        self, args: list[str], context: "CommandContext"
    ) -> None:
        domain = args[0].lower() if args else None

        if not self._discovery:
            await self._reply(context, error_msg("Discovery not available."))
            return

        if domain:
            entities = await self._discovery.get_entities_by_domain(domain)
            title = f"*{escape_md(domain)} entities*"
        else:
            entities = await self._discovery.get_all_states()
            title = "*All entities*"

        if not entities:
            await self._reply(context, escape_md(f"No entities found{f' for {domain}' if domain else ''}."))
            return

        page = 0
        if context.telegram_context and context.telegram_context.user_data:
            page = context.telegram_context.user_data.get("current_page", 0)

        page_items, keyboard = paginate(entities, page=page)

        lines = [title, ""]
        for e in page_items:
            eid = e.get("entity_id", "")
            state = e.get("state", "?")
            fname = e.get("attributes", {}).get("friendly_name", eid)
            unit = e.get("attributes", {}).get("unit_of_measurement", "")
            state_str = f"{state} {unit}".strip()
            lines.append(
                f"• {escape_md(fname)}\n  {code(eid)} → {code(state_str)}"
            )

        total = len(entities)
        lines.append(f"\n_{total} total entities_")

        await context.update.message.reply_text(
            "\n".join(lines),
            parse_mode=ParseMode.MARKDOWN_V2,
            reply_markup=keyboard,
        )

    async def _cmd_history(
        self, args: list[str], context: "CommandContext"
    ) -> None:
        if not args:
            await self._reply(context, "Usage: /history \\<entity\\_id\\> \\[hours\\]")
            return

        entity_id = args[0]
        hours = 24
        if len(args) > 1:
            try:
                hours = int(args[1])
            except ValueError:
                pass
        hours = max(1, min(hours, 168))  # 1 hour to 7 days

        try:
            history = await self._ha.get_history(entity_id, hours=hours)
        except Exception as exc:
            await self._reply(context, error_msg(f"Cannot get history: {exc}"))
            return

        if not history or not history[0]:
            await self._reply(context, escape_md(f"No history found for {entity_id}."))
            return

        entity_history = history[0]
        lines = [
            f"*History:* {code(entity_id)}",
            f"_Last {hours}h — {len(entity_history)} data points_",
            "",
        ]

        # Show last 15 state changes
        shown = entity_history[-15:]
        prev_state: str | None = None
        for entry in shown:
            state = entry.get("state", "?")
            ts = entry.get("last_changed", "")[:16].replace("T", " ")
            if state != prev_state:
                lines.append(f"`{escape_md(ts)}` → {code(state)}")
                prev_state = state

        await context.update.message.reply_text(
            "\n".join(lines),
            parse_mode=ParseMode.MARKDOWN_V2,
        )

    async def _reply(self, context: "CommandContext", text: str) -> None:
        await context.update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN_V2)
