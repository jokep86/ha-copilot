"""
System health dashboard — Phase 3.
/sys — component health, HA version, entity count, resource summary.
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


class SystemModule(ModuleBase):
    name = "system"
    description = "System health dashboard"
    commands: list[str] = ["sys"]

    async def setup(self, app: "AppContext") -> None:
        self._app = app
        self._ha = app.ha_client
        self._sup = app.supervisor_client
        self._deg = app.extra.get("degradation")

    async def teardown(self) -> None:
        pass

    async def handle_command(
        self, cmd: str, args: list[str], context: "CommandContext"
    ) -> None:
        await self._cmd_sys(context)

    # ------------------------------------------------------------------ #

    async def _cmd_sys(self, context: "CommandContext") -> None:
        lines: list[str] = [bold("System Health"), ""]

        # --- Component health from DegradationMap ---
        deg = self._app.extra.get("degradation")
        if deg:
            lines.append(bold("Components"))
            label = {
                "ha_api": "HA API",
                "supervisor_api": "Supervisor",
                "websocket": "WebSocket",
                "telegram": "Telegram",
                "claude": "Claude AI",
                "database": "Database",
            }
            for comp, name in label.items():
                emoji = deg.status_emoji(comp)
                err = deg.last_error(comp)
                line = f"{emoji} {escape_md(name)}"
                if err:
                    line += f" — {escape_md(err[:60])}"
                lines.append(line)
            lines.append("")

        # --- HA Core info ---
        try:
            ha_config = await self._ha.get_config()
            ha_ver = ha_config.get("version", "?")
            location = ha_config.get("location_name", "")
            lines.append(f"🏠 {bold('Home Assistant')} {code(ha_ver)}")
            if location:
                lines.append(f"   {escape_md(location)}")
        except Exception as exc:
            lines.append(f"🔴 HA config unavailable: {escape_md(str(exc)[:60])}")

        # --- Entity count ---
        try:
            discovery = self._app.extra.get("discovery")
            if discovery:
                domains = await discovery.get_domains()
                total = sum(domains.values())
                top = sorted(domains.items(), key=lambda x: -x[1])[:5]
                top_str = ", ".join(f"{d}:{n}" for d, n in top)
                lines.append(f"📊 {bold('Entities')} {code(str(total))} — {escape_md(top_str)}")
        except Exception:
            pass

        lines.append("")

        # --- Supervisor info ---
        try:
            sup_info = await self._sup.get_info()
            sup_ver = sup_info.get("version", "?")
            lines.append(f"🔧 {bold('Supervisor')} {code(sup_ver)}")
        except Exception as exc:
            lines.append(f"🔴 Supervisor unavailable: {escape_md(str(exc)[:60])}")

        # --- Host info ---
        try:
            host = await self._sup.get_host_info()
            hostname = host.get("hostname", "?")
            arch = host.get("chassis", host.get("operating_system", "?"))
            lines.append(f"🖥️ {bold('Host')} {escape_md(hostname)} — {escape_md(arch)}")
        except Exception:
            pass

        # --- OS info ---
        try:
            os_info = await self._sup.get_os_info()
            os_ver = os_info.get("version", "?")
            board = os_info.get("board", "")
            os_line = f"💽 {bold('HA OS')} {code(os_ver)}"
            if board:
                os_line += f" — {escape_md(board)}"
            lines.append(os_line)
        except Exception:
            pass

        await context.update.message.reply_text(
            "\n".join(lines),
            parse_mode=ParseMode.MARKDOWN_V2,
        )
