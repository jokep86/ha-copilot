"""
Jinja2 template testing with live preview — Phase 3.

/template {{ states("sensor.temp") }}
  → evaluate once and show result.

/template watch {{ states("sensor.temp") }}
  → re-evaluate every 5s for 60s, updating the message in-place.
"""
from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from telegram.constants import ParseMode

from app.bot.formatters import bold, code, error_msg, escape_md
from app.core.module_base import ModuleBase
from app.observability.logger import get_logger

if TYPE_CHECKING:
    from app.bot.handler import CommandContext
    from app.core.module_registry import AppContext

logger = get_logger(__name__)

WATCH_INTERVAL = 5   # seconds between re-evaluations
WATCH_DURATION = 60  # total watch time in seconds


class TemplateTesterModule(ModuleBase):
    name = "template_tester"
    description = "Jinja2 template testing"
    commands: list[str] = ["template"]

    async def setup(self, app: "AppContext") -> None:
        self._app = app
        self._ha = app.ha_client

    async def teardown(self) -> None:
        pass

    async def handle_command(
        self, cmd: str, args: list[str], context: "CommandContext"
    ) -> None:
        if not args:
            await self._reply(
                context,
                bold("Template Tester") + "\n"
                "Usage:\n"
                "`/template \\{\\{ states\\(\"sensor\\.temp\"\\) \\}\\}`\n"
                "`/template watch \\{\\{ states\\(\"sensor\\.temp\"\\) \\}\\}` \\(updates every 5s for 60s\\)",
            )
            return

        watch_mode = args[0].lower() == "watch"
        template_args = args[1:] if watch_mode else args
        template = " ".join(template_args)

        if not template.strip():
            await self._reply(context, error_msg("Empty template."))
            return

        if watch_mode:
            await self._cmd_watch(template, context)
        else:
            await self._cmd_evaluate(template, context)

    # ------------------------------------------------------------------ #

    async def _cmd_evaluate(self, template: str, context: "CommandContext") -> None:
        try:
            result = await self._ha.render_template(template)
        except Exception as exc:
            await self._reply(context, error_msg(f"Template error: {exc}"))
            return

        await context.update.message.reply_text(
            f"{bold('Result')}\n{code(escape_md(result))}",
            parse_mode=ParseMode.MARKDOWN_V2,
        )

    async def _cmd_watch(self, template: str, context: "CommandContext") -> None:
        # Send initial evaluation as a new message, then edit in-place
        try:
            result = await self._ha.render_template(template)
        except Exception as exc:
            await self._reply(context, error_msg(f"Template error: {exc}"))
            return

        msg = await context.update.message.reply_text(
            self._format_watch(template, result, iteration=1),
            parse_mode=ParseMode.MARKDOWN_V2,
        )

        iterations = WATCH_DURATION // WATCH_INTERVAL
        for i in range(2, iterations + 2):
            await asyncio.sleep(WATCH_INTERVAL)
            try:
                result = await self._ha.render_template(template)
            except Exception as exc:
                result = f"Error: {exc}"

            try:
                await msg.edit_text(
                    self._format_watch(template, result, iteration=i),
                    parse_mode=ParseMode.MARKDOWN_V2,
                )
            except Exception:
                # Message may have been deleted or edit failed — stop watching
                break

        # Final update marking watch complete
        try:
            await msg.edit_text(
                self._format_watch(template, result, iteration=i, done=True),
                parse_mode=ParseMode.MARKDOWN_V2,
            )
        except Exception:
            pass

        logger.info("template_watch_done", user_id=context.user_id)

    def _format_watch(
        self, template: str, result: str, iteration: int, done: bool = False
    ) -> str:
        status = "✅ done" if done else f"🔄 {iteration * WATCH_INTERVAL}s"
        tmpl_display = template[:60] + ("…" if len(template) > 60 else "")
        return (
            f"{bold('Watch')} {code(escape_md(tmpl_display))} \\[{escape_md(status)}\\]\n"
            f"{code(escape_md(result))}"
        )

    async def _reply(self, context: "CommandContext", text: str) -> None:
        await context.update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN_V2)
