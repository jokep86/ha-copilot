"""
Configuration management — Phase 6.

/config [show]   — display configuration.yaml (truncated)
/config check    — validate configuration via HA API
/integrations    — list configured integrations (config entries)
/users           — list HA users (via WS auth/list_users)
"""
from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from telegram.constants import ParseMode

from app.bot.formatters import bold, code, error_msg, escape_md, success_msg
from app.core.module_base import ModuleBase
from app.observability.logger import get_logger

if TYPE_CHECKING:
    from app.bot.handler import CommandContext
    from app.core.module_registry import AppContext

logger = get_logger(__name__)

# HA add-on: homeassistant_config mapped to /homeassistant
_CONFIG_FILE = Path("/homeassistant/configuration.yaml")
# Telegram message limit minus some headroom
_MAX_YAML_CHARS = 3800


class ConfigManagerModule(ModuleBase):
    name = "config_manager"
    description = "configuration.yaml and integrations"
    commands: list[str] = ["config", "integrations", "users"]

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
        if cmd == "integrations":
            await self._cmd_integrations(context)
        elif cmd == "users":
            await self._cmd_users(context)
        else:
            # /config [show|check]
            sub = args[0].lower() if args else "show"
            if sub == "check":
                await self._cmd_check(context)
            else:
                await self._cmd_show(context)

    # ------------------------------------------------------------------ #

    async def _cmd_show(self, context: "CommandContext") -> None:
        if not _CONFIG_FILE.exists():
            await self._reply(
                context, error_msg(f"Config file not found: {_CONFIG_FILE}")
            )
            return

        try:
            content = _CONFIG_FILE.read_text(encoding="utf-8")
        except OSError as exc:
            await self._reply(context, error_msg(f"Cannot read config file: {exc}"))
            return

        truncated = ""
        if len(content) > _MAX_YAML_CHARS:
            content = content[:_MAX_YAML_CHARS]
            truncated = f"\n\n_\\.\\.\\. truncated at {_MAX_YAML_CHARS} chars_"

        # Escape backticks for code block
        safe = content.replace("\\", "\\\\").replace("`", "\\`")
        msg = f"```yaml\n{safe}\n```{truncated}"
        await context.update.message.reply_text(
            msg, parse_mode=ParseMode.MARKDOWN_V2
        )

    async def _cmd_check(self, context: "CommandContext") -> None:
        try:
            result = await self._ha.check_config()
        except Exception as exc:
            await self._reply(context, error_msg(f"Check failed: {exc}"))
            return

        # HA returns {"result": "valid"|"invalid", "errors": "..."}
        outcome = result.get("result", "unknown") if isinstance(result, dict) else "unknown"
        errors = result.get("errors", "") if isinstance(result, dict) else str(result)

        if outcome == "valid":
            await self._reply(context, success_msg("Configuration is valid."))
        else:
            msg = f"🔴 Config check failed\\:\n{escape_md(str(errors))}"
            await self._reply(context, msg)

    async def _cmd_integrations(self, context: "CommandContext") -> None:
        try:
            entries = await self._ha.get_config_entries()
        except Exception as exc:
            await self._reply(context, error_msg(f"Could not fetch integrations: {exc}"))
            return

        if not entries:
            await self._reply(context, "No integrations found\\.")
            return

        # Group by domain for a compact listing
        by_domain: dict[str, list[str]] = {}
        for e in entries:
            domain = e.get("domain", "unknown")
            title = e.get("title", "") or e.get("domain", "")
            by_domain.setdefault(domain, []).append(title)

        lines = [bold(f"Integrations \\({len(entries)}\\)"), ""]
        for domain, titles in sorted(by_domain.items()):
            unique = sorted(set(titles))
            label = ", ".join(escape_md(t) for t in unique[:3])
            if len(unique) > 3:
                label += f", \\+{len(unique) - 3} more"
            lines.append(f"• {code(domain)}: {label}")

        await context.update.message.reply_text(
            "\n".join(lines), parse_mode=ParseMode.MARKDOWN_V2
        )

    async def _cmd_users(self, context: "CommandContext") -> None:
        ws = self._app.extra.get("websocket")
        if not ws:
            await self._reply(context, error_msg("WebSocket not available."))
            return

        try:
            from app.ha.websocket import WebSocketError

            users = await ws.send_command({"type": "auth/list_users"})
        except Exception as exc:
            await self._reply(context, error_msg(f"Could not fetch users: {exc}"))
            return

        if not users:
            await self._reply(context, "No users found\\.")
            return

        lines = [bold(f"HA Users \\({len(users)}\\)"), ""]
        for u in users:
            name = escape_md(u.get("name", "unknown"))
            system = " _(system)_" if u.get("system_generated") else ""
            active = "" if u.get("is_active", True) else " 🔴"
            is_admin = " 👑" if u.get("group_ids") and "system-admin" in (u.get("group_ids") or []) else ""
            lines.append(f"• {name}{is_admin}{active}{system}")

        await context.update.message.reply_text(
            "\n".join(lines), parse_mode=ParseMode.MARKDOWN_V2
        )

    async def _reply(self, context: "CommandContext", text: str) -> None:
        await context.update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN_V2)
