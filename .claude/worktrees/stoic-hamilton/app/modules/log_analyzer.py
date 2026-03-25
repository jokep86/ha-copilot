"""
Log reading and AI analysis — Phase 3.
/logs [source] [level] — read logs from core/supervisor/host/<addon-slug>.
/logs analyze [source] — Claude AI diagnosis of recent errors.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import TYPE_CHECKING

from telegram.constants import ParseMode

from app.bot.formatters import bold, code, error_msg, escape_md
from app.core.module_base import ModuleBase
from app.observability.logger import get_logger

if TYPE_CHECKING:
    from app.bot.handler import CommandContext
    from app.core.module_registry import AppContext

logger = get_logger(__name__)

PROMPT_PATH = Path("/app/prompts/v1/log_analyzer.txt")
MAX_LOG_LINES = 200   # lines shown to user
MAX_AI_CHARS = 6000   # chars sent to Claude


class LogAnalyzerModule(ModuleBase):
    name = "log_analyzer"
    description = "Log reading and AI analysis"
    commands: list[str] = ["logs"]

    async def setup(self, app: "AppContext") -> None:
        self._app = app
        self._sup = app.supervisor_client

        import anthropic
        self._ai = anthropic.AsyncAnthropic(api_key=app.config.anthropic_api_key)

        if PROMPT_PATH.exists():
            self._prompt = PROMPT_PATH.read_text()
        else:
            logger.warning("log_analyzer_prompt_missing", path=str(PROMPT_PATH))
            self._prompt = (
                "Analyze the following Home Assistant log snippet. "
                "Identify errors, root cause, affected component, and recommended action.\n\n"
                "Log:\n{log_snippet}"
            )

    async def teardown(self) -> None:
        pass

    async def handle_command(
        self, cmd: str, args: list[str], context: "CommandContext"
    ) -> None:
        # /logs analyze [source]
        if args and args[0] == "analyze":
            source = args[1] if len(args) > 1 else "core"
            await self._cmd_analyze(source, context)
            return

        # /logs [source] [level]
        source = args[0] if args else "core"
        level = args[1].upper() if len(args) > 1 else None
        await self._cmd_logs(source, level, context)

    # ------------------------------------------------------------------ #

    async def _cmd_logs(
        self, source: str, level: str | None, context: "CommandContext"
    ) -> None:
        try:
            raw = await self._sup.get_logs(source)
        except Exception as exc:
            await self._reply(context, error_msg(f"Cannot get logs from '{source}': {exc}"))
            return

        lines = raw.splitlines()

        # Level filter
        if level:
            lines = [l for l in lines if level in l.upper()]

        lines = lines[-MAX_LOG_LINES:]
        if not lines:
            await self._reply(
                context,
                escape_md(f"No {'log lines' if not level else level + ' entries'} found for {source}."),
            )
            return

        text = "\n".join(lines)
        # Telegram max message is 4096 chars — truncate and send as code block
        if len(text) > 3800:
            text = "…" + text[-(3800):]

        header = bold(f"Logs: {escape_md(source)}")
        if level:
            header += f" \\[{escape_md(level)}\\]"
        header += f" \\({len(lines)} lines\\)"

        await context.update.message.reply_text(
            f"{header}\n```\n{text}\n```",
            parse_mode=ParseMode.MARKDOWN_V2,
        )

    async def _cmd_analyze(self, source: str, context: "CommandContext") -> None:
        try:
            raw = await self._sup.get_logs(source)
        except Exception as exc:
            await self._reply(context, error_msg(f"Cannot get logs from '{source}': {exc}"))
            return

        # Extract only error/warning lines for AI analysis
        lines = raw.splitlines()
        error_lines = [
            l for l in lines
            if re.search(r"\b(ERROR|WARNING|CRITICAL|FATAL|exception|traceback)",
                         l, re.IGNORECASE)
        ]

        if not error_lines:
            await self._reply(context, escape_md(f"No errors found in {source} logs. ✅"))
            return

        snippet = "\n".join(error_lines[-100:])
        snippet = snippet[:MAX_AI_CHARS]

        if not self._app.config.ai_enabled:
            await self._reply(
                context,
                "AI is disabled\\. Enable `ai_enabled` to analyze logs\\.",
            )
            return

        await self._reply(context, f"🤖 Analyzing {code(source)} logs…")

        prompt = self._prompt.replace("{log_snippet}", snippet)
        try:
            response = await self._ai.messages.create(
                model=self._app.config.ai_model,
                max_tokens=self._app.config.ai_max_tokens,
                messages=[{"role": "user", "content": prompt}],
            )
            analysis = response.content[0].text if response.content else "No analysis available."
            logger.info(
                "log_analysis_done",
                source=source,
                input_tokens=response.usage.input_tokens,
                output_tokens=response.usage.output_tokens,
            )
        except Exception as exc:
            logger.error("log_analysis_failed", error=str(exc))
            await self._reply(context, error_msg(f"AI analysis failed: {exc}"))
            return

        # Send as plain text (analysis may use markdown-like formatting)
        # Escape for MarkdownV2
        await context.update.message.reply_text(
            f"{bold('Log Analysis')} — {code(source)}\n\n{escape_md(analysis)}",
            parse_mode=ParseMode.MARKDOWN_V2,
        )

    async def _reply(self, context: "CommandContext", text: str) -> None:
        await context.update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN_V2)
