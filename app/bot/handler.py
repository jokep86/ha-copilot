"""
Telegram bot setup, command routing, and message dispatch.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Optional

from telegram import BotCommand, Update
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from app.bot.callbacks import handle_callback_query
from app.bot.formatters import escape_md
from app.observability.logger import get_logger

if TYPE_CHECKING:
    from app.config import AppConfig
    from app.core.command_queue import CommandQueueManager
    from app.core.degradation import DegradationMap
    from app.core.module_registry import ModuleRegistry
    from app.database import Database
    from app.middleware.auth import AuthMiddleware
    from app.observability.health import DeadManSwitch

logger = get_logger(__name__)

VERSION = "0.1.0"

_HELP_TEXT = """\
*HA Copilot v{version}* — Home Assistant AI Admin

*Devices & Entities*
/devices \\[domain\\] — List & control devices
/status \\<entity\\> — Entity state
/entities \\[domain\\] — List entities
/history \\<entity\\> \\[hours\\] — State history

*Automations & Scenes*
/auto — List / create / edit automations \\(supports choose, repeat, parallel\\)
/scenes — List / create scenes
/schedule — Scheduled commands
/explain — AI documentation

*Config & Dashboard*
/config — Show / check configuration\\.yaml
/integrations — Installed integrations
/users — HA users
/dash — Lovelace dashboards

*System*
/sys — System health
/logs \\[source\\] — System logs
/addons — Add\\-ons
/backup — Backups
/restart — Restart core/supervisor
/reboot — Host reboot

*Media & Data*
/camera \\<entity\\> — Camera snapshot
/chart \\<entity\\> \\[hours\\] — History chart
/export automations\\|scenes\\|config — Export file
/snapshot — Entity snapshots
/energy — Energy reports

*Alerts & Notifications*
/alerts — Recent alerts
/notify — Notification settings
/subs — Active subscriptions

*Tools*
/raw \\<method\\> \\<path\\> — Direct API call
/template \\<jinja2\\> — Test template
/migrate — Migration check
/quick — Quick action shortcuts
/audit export \\[days\\] — Audit log export
/undo — Undo last action

_Just type naturally — AI handles it\\._\
"""

_WELCOME_TEXT = """\
👋 *Welcome back to HA Copilot v{version}\\!*

Type /help for commands, or just start talking\\.\
"""

_WIZARD_TEXT = """\
🏠 *Welcome to HA Copilot v{version}\\!*

Your full Home Assistant administration assistant via Telegram\\.

*What you can do:*
• 💡 _"turn on the living room light"_ — control any device
• 🤖 _"create an automation that turns off lights at midnight"_
• 📊 _"what's the temperature in the bedroom?"_
• 🔍 _"why is zigbee2mqtt crashing?"_ — AI log analysis
• 📸 /camera, /chart, /energy, /snapshot — media & data

*Getting started:*
1\\. Type /devices to see all your devices
2\\. Type /sys for system health
3\\. Or just type naturally — the AI handles it

*Quick tips:*
• Fuzzy matching: "living room" finds `light\\.living_room`
• /auto to manage automations
• /help for the full command list

✅ Setup complete\\. Happy home automating\\!\
"""


@dataclass
class CommandContext:
    """Context passed to every module handler via the command queue."""

    update: Update
    telegram_context: ContextTypes.DEFAULT_TYPE
    user_id: int
    chat_id: int
    trace_id: str = field(default="")


class BotHandler:
    """Sets up the Telegram Application and routes updates to modules."""

    def __init__(
        self,
        config: "AppConfig",
        module_registry: "ModuleRegistry",
        command_queue: "CommandQueueManager",
        auth: "AuthMiddleware",
        degradation: "DegradationMap",
        dead_man_switch: "DeadManSwitch",
        db: "Database | None" = None,
    ) -> None:
        self.config = config
        self.registry = module_registry
        self.queue = command_queue
        self.auth = auth
        self.degradation = degradation
        self.dms = dead_man_switch
        self.db = db
        self._app: Optional[Application] = None

    async def setup(self) -> None:
        """Build Application, register all handlers, set bot commands."""
        self._app = Application.builder().token(self.config.telegram_bot_token).build()

        # Core commands handled directly here
        self._app.add_handler(CommandHandler("start", self._handle_start))
        self._app.add_handler(CommandHandler("help", self._handle_help))

        # All other commands routed to modules
        self._app.add_handler(
            MessageHandler(filters.COMMAND & ~filters.Regex(r"^/(start|help)"), self._handle_command)
        )

        # Inline keyboard callbacks
        self._app.add_handler(CallbackQueryHandler(handle_callback_query))

        # Free-text NL → AI engine (Phase 2)
        self._app.add_handler(
            MessageHandler(filters.TEXT & ~filters.COMMAND, self._handle_text)
        )

        # Global error handler — catches all unhandled exceptions in handlers
        self._app.add_error_handler(self._handle_error)

        # Set visible bot command menu
        await self._app.bot.set_my_commands(
            [
                BotCommand("start", "Welcome"),
                BotCommand("help", "Command reference"),
                BotCommand("sys", "System health"),
                BotCommand("devices", "Device control"),
                BotCommand("auto", "Automations"),
                BotCommand("scenes", "Scenes"),
                BotCommand("logs", "System logs"),
                BotCommand("addons", "Add-ons"),
                BotCommand("backup", "Backups"),
                BotCommand("alerts", "Active alerts"),
            ]
        )

        self.degradation.set_healthy("telegram")
        logger.info("bot_handler_ready")

    async def start_polling(self) -> None:
        if not self._app:
            raise RuntimeError("BotHandler.setup() must be called first")
        await self._app.initialize()
        await self._app.start()
        await self._app.updater.start_polling(drop_pending_updates=True)
        logger.info("bot_polling_started")

    async def stop(self) -> None:
        if self._app:
            try:
                if self._app.updater and self._app.updater.running:
                    await self._app.updater.stop()
                await self._app.stop()
                await self._app.shutdown()
            except Exception as exc:
                logger.warning("bot_stop_error", error=str(exc))

    async def send_message(
        self,
        chat_id: int,
        text: str,
        parse_mode: str = ParseMode.MARKDOWN_V2,
    ) -> None:
        """Send a message to a chat. Safe to call from modules."""
        if not self._app:
            return
        try:
            await self._app.bot.send_message(
                chat_id=chat_id, text=text, parse_mode=parse_mode
            )
        except Exception as exc:
            logger.error("send_message_failed", chat_id=chat_id, error=str(exc))

    async def broadcast(self, text: str) -> None:
        """Send plain text to all allowed Telegram IDs."""
        for uid in self.config.allowed_telegram_ids:
            await self.send_message(uid, text, parse_mode=ParseMode.MARKDOWN_V2)

    # --- Error handler ---

    async def _handle_error(
        self, update: object, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Global Telegram error handler — log every unhandled exception."""
        logger.error(
            "unhandled_telegram_error",
            error=str(context.error),
            update=str(update)[:200],
        )
        # Notify the user if possible
        if isinstance(update, Update) and update.effective_message:
            try:
                await update.effective_message.reply_text(
                    "🔴 Something went wrong processing your request\\. Please try again\\.",
                    parse_mode=ParseMode.MARKDOWN_V2,
                )
            except Exception:
                pass  # Don't recurse if the reply itself fails

    # --- Update handlers ---

    async def _auth_check(self, update: Update) -> bool:
        return await self.auth.check(update)

    async def _handle_start(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        if not await self._auth_check(update):
            return

        # Show the onboarding wizard on first run, then a short welcome.
        if self.db:
            onboarded = await self.db.get_setting("onboarded")
            if not onboarded:
                await self.db.set_setting("onboarded", "1")
                await update.message.reply_text(
                    _WIZARD_TEXT.format(version=escape_md(VERSION)),
                    parse_mode=ParseMode.MARKDOWN_V2,
                )
                return

        await update.message.reply_text(
            _WELCOME_TEXT.format(version=escape_md(VERSION)),
            parse_mode=ParseMode.MARKDOWN_V2,
        )

    async def _handle_help(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        if not await self._auth_check(update):
            return
        await update.message.reply_text(
            _HELP_TEXT.format(version=escape_md(VERSION)),
            parse_mode=ParseMode.MARKDOWN_V2,
        )

    async def _handle_command(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        if not await self._auth_check(update):
            return
        if not update.message or not update.message.text:
            return

        parts = update.message.text.split()
        # Strip leading / and optional @BotUsername suffix
        raw_cmd = parts[0].lstrip("/")
        cmd = raw_cmd.split("@")[0]
        args = parts[1:]

        user_id = update.effective_user.id
        chat_id = update.effective_chat.id

        module = self.registry.get_module_for_command(cmd)
        if not module:
            await update.message.reply_text(
                f"Unknown command: /{escape_md(cmd)}\nType /help for available commands\\.",
                parse_mode=ParseMode.MARKDOWN_V2,
            )
            return

        ctx = CommandContext(
            update=update,
            telegram_context=context,
            user_id=user_id,
            chat_id=chat_id,
        )
        accepted = await self.queue.dispatch(
            user_id=user_id,
            cmd=cmd,
            args=args,
            context=ctx,
            handler=module.handle_command,
            dead_man_switch=self.dms,
        )
        if not accepted:
            await update.message.reply_text(
                "🔴 Too many pending commands\\. Please wait\\.",
                parse_mode=ParseMode.MARKDOWN_V2,
            )

    async def _handle_text(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        if not await self._auth_check(update):
            return
        if not update.message:
            return

        user_id = update.effective_user.id
        chat_id = update.effective_chat.id

        # Route to AI engine module (registered as "ai_nl" command in Phase 2)
        ai_module = self.registry.get_module_for_command("ai_nl")
        if ai_module:
            ctx = CommandContext(
                update=update,
                telegram_context=context,
                user_id=user_id,
                chat_id=chat_id,
            )
            await self.queue.dispatch(
                user_id=user_id,
                cmd="ai_nl",
                args=[update.message.text or ""],
                context=ctx,
                handler=ai_module.handle_command,
                dead_man_switch=self.dms,
            )
        else:
            await update.message.reply_text(
                "🤖 AI engine not available yet\\. Use /help for structured commands\\.",
                parse_mode=ParseMode.MARKDOWN_V2,
            )
