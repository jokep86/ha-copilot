"""
Add-ons, backups, restarts, and resource monitoring — Phase 3.
/addons — list all add-ons with status.
/addon <slug> restart|info — manage a specific add-on.
/backup list|create — backup management.
/restart core|supervisor — restart HA core or Supervisor (double confirm).
/reboot — host reboot (double confirm).
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

# Slugs that must not be restarted autonomously
_PROTECTED_ADDONS = {"hassio_supervisor", "core_homeassistant"}


class SupervisorManagerModule(ModuleBase):
    name = "supervisor_mgr"
    description = "Add-ons, backups, restarts, resources"
    commands: list[str] = ["addons", "addon", "backup", "restart", "reboot"]

    async def setup(self, app: "AppContext") -> None:
        self._app = app
        self._sup = app.supervisor_client

    async def teardown(self) -> None:
        pass

    async def handle_command(
        self, cmd: str, args: list[str], context: "CommandContext"
    ) -> None:
        if cmd == "addons":
            await self._cmd_addons(context)
        elif cmd == "addon":
            await self._cmd_addon(args, context)
        elif cmd == "backup":
            await self._cmd_backup(args, context)
        elif cmd == "restart":
            await self._cmd_restart(args, context)
        elif cmd == "reboot":
            await self._cmd_reboot(args, context)

    # ------------------------------------------------------------------ #

    async def _cmd_addons(self, context: "CommandContext") -> None:
        try:
            addons = await self._sup.get_addons()
        except Exception as exc:
            await self._reply(context, error_msg(f"Cannot list add-ons: {exc}"))
            return

        if not addons:
            await self._reply(context, "No add-ons found.")
            return

        lines = [bold("Add-ons"), ""]
        for a in sorted(addons, key=lambda x: x.get("name", "")):
            name = a.get("name", a.get("slug", "?"))
            slug = a.get("slug", "?")
            state = a.get("state", "?")
            version = a.get("version", "?")
            update = " ⬆️" if a.get("update_available") else ""
            icon = "🟢" if state == "started" else "🔴"
            lines.append(
                f"{icon} {escape_md(name)}{update}\n"
                f"   {code(slug)} v{escape_md(version)}"
            )

        lines.append(f"\n_{len(addons)} total_")
        await context.update.message.reply_text(
            "\n".join(lines), parse_mode=ParseMode.MARKDOWN_V2
        )

    async def _cmd_addon(self, args: list[str], context: "CommandContext") -> None:
        if len(args) < 2:
            await self._reply(
                context,
                "Usage: /addon \\<slug\\> restart\\|info",
            )
            return

        slug, action = args[0], args[1].lower()

        if action == "info":
            try:
                info = await self._sup.get_addon_info(slug)
            except Exception as exc:
                await self._reply(context, error_msg(f"Cannot get add-on info: {exc}"))
                return
            name = info.get("name", slug)
            state = info.get("state", "?")
            version = info.get("version", "?")
            description = info.get("description", "")
            lines = [
                bold(escape_md(name)),
                f"Slug: {code(slug)}",
                f"State: {code(state)}",
                f"Version: {code(version)}",
            ]
            if description:
                lines.append(f"_{escape_md(description[:120])}_")
            await context.update.message.reply_text(
                "\n".join(lines), parse_mode=ParseMode.MARKDOWN_V2
            )

        elif action == "restart":
            if slug in _PROTECTED_ADDONS:
                await self._reply(
                    context,
                    error_msg(f"'{slug}' is protected — use /restart core or /restart supervisor."),
                )
                return
            # Double confirm: first call sends warning, second (with "confirm") executes
            if len(args) < 3 or args[2] != "confirm":
                await self._reply(
                    context,
                    f"⚠️ Restart add\\-on {code(slug)}\\?\n"
                    f"Send `/addon {escape_md(slug)} restart confirm` to proceed\\.",
                )
                return
            try:
                await self._sup.restart_addon(slug)
                await self._reply(context, success_msg(f"Add-on '{slug}' restarted."))
            except Exception as exc:
                await self._reply(context, error_msg(f"Restart failed: {exc}"))

        else:
            await self._reply(context, f"Unknown action: {code(action)}\\. Use restart or info\\.")

    async def _cmd_backup(self, args: list[str], context: "CommandContext") -> None:
        action = args[0].lower() if args else "list"

        if action == "list":
            try:
                backups = await self._sup.get_backups()
            except Exception as exc:
                await self._reply(context, error_msg(f"Cannot list backups: {exc}"))
                return

            if not backups:
                await self._reply(context, "No backups found.")
                return

            lines = [bold("Backups"), ""]
            for b in backups[:10]:
                name = b.get("name", b.get("slug", "?"))
                date = b.get("date", "?")[:10]
                size_mb = round(b.get("size", 0) / 1024 / 1024, 1) if b.get("size") else "?"
                btype = b.get("type", "full")
                lines.append(
                    f"💾 {escape_md(name)}\n"
                    f"   {escape_md(date)} — {escape_md(str(size_mb))} MB — {escape_md(btype)}"
                )
            if len(backups) > 10:
                lines.append(f"\n_… and {len(backups) - 10} more_")

            await context.update.message.reply_text(
                "\n".join(lines), parse_mode=ParseMode.MARKDOWN_V2
            )

        elif action == "create":
            await self._reply(context, "⏳ Creating full backup… this may take a minute\\.")
            try:
                result = await self._sup.create_backup()
                slug = result.get("slug", "?")
                await self._reply(context, success_msg(f"Backup created: {slug}"))
            except Exception as exc:
                await self._reply(context, error_msg(f"Backup failed: {exc}"))

        else:
            await self._reply(context, "Usage: /backup list\\|create")

    async def _cmd_restart(self, args: list[str], context: "CommandContext") -> None:
        if not args:
            await self._reply(
                context,
                "Usage: /restart core\\|supervisor\n"
                "Add `confirm` to execute: `/restart core confirm`",
            )
            return

        target = args[0].lower()
        if target not in ("core", "supervisor"):
            await self._reply(
                context, error_msg(f"Unknown target '{target}'. Use core or supervisor.")
            )
            return

        confirmed = len(args) >= 2 and args[1] == "confirm"
        if not confirmed:
            await self._reply(
                context,
                f"⚠️ Restart {bold(escape_md(target))}\\?\n"
                f"Send `/restart {escape_md(target)} confirm` to proceed\\.",
            )
            return

        try:
            await self._reply(context, f"⏳ Restarting {code(target)}…")
            if target == "core":
                await self._sup.restart_core()
            else:
                # Restart supervisor via addon restart of self
                await self._sup.restart_addon("core_supervisor")
            await self._reply(context, success_msg(f"Restart command sent for {target}."))
        except Exception as exc:
            await self._reply(context, error_msg(f"Restart failed: {exc}"))

        logger.info("restart_executed", target=target, user_id=context.user_id)

    async def _cmd_reboot(self, args: list[str], context: "CommandContext") -> None:
        confirmed = args and args[0] == "confirm"
        if not confirmed:
            await self._reply(
                context,
                "⚠️ *Host reboot* — this will reboot the entire server\\!\n"
                "Send `/reboot confirm` to proceed\\.",
            )
            return

        try:
            await self._reply(context, "⏳ Sending reboot command…")
            await self._sup.reboot_host()
            await self._reply(context, success_msg("Host reboot initiated."))
        except Exception as exc:
            await self._reply(context, error_msg(f"Reboot failed: {exc}"))

        logger.info("host_reboot_executed", user_id=context.user_id)

    async def _reply(self, context: "CommandContext", text: str) -> None:
        await context.update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN_V2)
