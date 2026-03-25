"""
Device control module — Phase 2.
/devices [domain] — paginated list with inline toggle buttons.
/status <entity_id> — detailed entity state.
/toggle <entity_id> — quick toggle.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode

from app.bot.formatters import code, entity_state_msg, error_msg, escape_md
from app.bot.pagination import paginate
from app.core.module_base import ModuleBase
from app.observability.logger import get_logger

if TYPE_CHECKING:
    from app.bot.handler import CommandContext
    from app.core.module_registry import AppContext

logger = get_logger(__name__)

_TOGGLEABLE = {
    "light", "switch", "fan", "media_player", "input_boolean", "automation",
}
_ON_SERVICE: dict[str, tuple[str, str]] = {
    "light": ("light", "turn_on"),
    "switch": ("switch", "turn_on"),
    "fan": ("fan", "turn_on"),
    "media_player": ("media_player", "media_play"),
    "input_boolean": ("input_boolean", "turn_on"),
    "automation": ("automation", "turn_on"),
}
_OFF_SERVICE: dict[str, tuple[str, str]] = {
    "light": ("light", "turn_off"),
    "switch": ("switch", "turn_off"),
    "fan": ("fan", "turn_off"),
    "media_player": ("media_player", "media_pause"),
    "input_boolean": ("input_boolean", "turn_off"),
    "automation": ("automation", "turn_off"),
}


class DevicesModule(ModuleBase):
    name = "devices"
    description = "Device listing and control with inline keyboards"
    commands: list[str] = ["devices", "status", "toggle"]

    async def setup(self, app: "AppContext") -> None:
        self._app = app
        self._ha = app.ha_client
        self._discovery = app.extra.get("discovery")

    async def teardown(self) -> None:
        pass

    async def handle_command(
        self, cmd: str, args: list[str], context: "CommandContext"
    ) -> None:
        if cmd == "status":
            await self._cmd_status(args, context)
        elif cmd == "toggle":
            await self._cmd_toggle(args, context)
        else:
            await self._cmd_devices(args, context)

    # ------------------------------------------------------------------ #

    async def _cmd_devices(
        self, args: list[str], context: "CommandContext"
    ) -> None:
        domain = args[0].lower() if args else None

        if not self._discovery:
            await self._reply(context, error_msg("Discovery not available."))
            return

        if not domain:
            await self._send_domain_summary(context)
            return

        entities = await self._discovery.get_entities_by_domain(domain)
        if not entities:
            await self._reply(
                context, escape_md(f"No entities found for domain '{domain}'.")
            )
            return

        page = 0
        if context.telegram_context and context.telegram_context.user_data:
            page = context.telegram_context.user_data.get("current_page", 0)

        page_entities, nav_keyboard = paginate(entities, page=page)

        lines = [f"*{escape_md(domain)} devices*"]
        for e in page_entities:
            eid = e.get("entity_id", "")
            state = e.get("state", "?")
            fname = e.get("attributes", {}).get("friendly_name", eid)
            icon = "🟢" if state in ("on", "home", "open", "playing", "heating") else "⚪"
            lines.append(f"{icon} {escape_md(fname)} — {code(state)}")

        # Build toggle buttons for toggleable domains
        keyboard = None
        if domain in _TOGGLEABLE and page_entities:
            toggle_rows = []
            row: list[InlineKeyboardButton] = []
            for e in page_entities[:6]:
                eid = e.get("entity_id", "")
                fname = e.get("attributes", {}).get("friendly_name", eid)
                state = e.get("state", "?")
                icon = "🔴" if state == "on" else "⚫"
                row.append(
                    InlineKeyboardButton(
                        f"{icon} {fname[:14]}", callback_data=f"toggle:{eid}"
                    )
                )
                if len(row) == 2:
                    toggle_rows.append(row)
                    row = []
            if row:
                toggle_rows.append(row)
            if nav_keyboard:
                toggle_rows.append(nav_keyboard.inline_keyboard[0])
            keyboard = InlineKeyboardMarkup(toggle_rows)
        elif nav_keyboard:
            keyboard = nav_keyboard

        await context.update.message.reply_text(
            "\n".join(lines),
            parse_mode=ParseMode.MARKDOWN_V2,
            reply_markup=keyboard,
        )

    async def _send_domain_summary(self, context: "CommandContext") -> None:
        if not self._discovery:
            await self._reply(context, "Discovery not available.")
            return
        domains = await self._discovery.get_domains()
        if not domains:
            await self._reply(context, "No entities found in Home Assistant.")
            return

        sorted_domains = sorted(domains.items(), key=lambda x: -x[1])
        lines = ["*Device domains*", ""]
        buttons: list[InlineKeyboardButton] = []
        for domain, count in sorted_domains[:15]:
            lines.append(f"• {escape_md(domain)}: {count} entities")
            buttons.append(
                InlineKeyboardButton(
                    f"{domain} ({count})", callback_data=f"domain:{domain}"
                )
            )

        rows = [buttons[i : i + 2] for i in range(0, len(buttons), 2)]
        keyboard = InlineKeyboardMarkup(rows) if rows else None

        await context.update.message.reply_text(
            "\n".join(lines),
            parse_mode=ParseMode.MARKDOWN_V2,
            reply_markup=keyboard,
        )

    async def _cmd_status(
        self, args: list[str], context: "CommandContext"
    ) -> None:
        if not args:
            await self._reply(context, "Usage: /status \\<entity\\_id\\>")
            return
        entity_id = args[0]
        try:
            state = await self._ha.get_state(entity_id)
            text = entity_state_msg(
                state["entity_id"], state["state"], state.get("attributes", {})
            )
            await context.update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN_V2)
        except Exception as exc:
            await self._reply(
                context, error_msg(f"Cannot get state for '{entity_id}': {exc}")
            )

    async def _cmd_toggle(
        self, args: list[str], context: "CommandContext"
    ) -> None:
        if not args:
            await self._reply(context, "Usage: /toggle \\<entity\\_id\\>")
            return
        await self._do_toggle(args[0], context)

    async def _do_toggle(self, entity_id: str, context: "CommandContext") -> None:
        domain = entity_id.split(".")[0]
        try:
            state_data = await self._ha.get_state(entity_id)
            current = state_data.get("state", "off")
            if current == "on":
                svc_domain, service = _OFF_SERVICE.get(domain, (domain, "turn_off"))
            else:
                svc_domain, service = _ON_SERVICE.get(domain, (domain, "turn_on"))
            await self._ha.call_service(svc_domain, service, {"entity_id": entity_id})
            new = "off" if current == "on" else "on"
            fname = state_data.get("attributes", {}).get("friendly_name", entity_id)
            icon = "🔴" if new == "off" else "🟢"
            await self._reply(context, f"{icon} {escape_md(fname)} → {code(new)}")
        except Exception as exc:
            await self._reply(context, error_msg(f"Toggle failed: {exc}"))

    async def _reply(self, context: "CommandContext", text: str) -> None:
        await context.update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN_V2)
