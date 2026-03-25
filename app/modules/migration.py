"""
Migration assistant — Phase 8.

/migrate check   — Claude analyzes config + integrations for deprecated/breaking patterns
/migrate         — same as /migrate check
"""
from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import anthropic
from telegram.constants import ParseMode

from app.bot.formatters import bold, code, error_msg, escape_md, warning_msg
from app.core.module_base import ModuleBase
from app.observability.logger import get_logger

if TYPE_CHECKING:
    from app.bot.handler import CommandContext
    from app.core.module_registry import AppContext

logger = get_logger(__name__)

_CONFIG_FILE = Path("/homeassistant/configuration.yaml")
_PROMPT_FILE = Path("/app/prompts/v1/migration_checker.txt")
_CONFIG_SNIPPET_CHARS = 3000
_MAX_INTEGRATIONS = 50


class MigrationModule(ModuleBase):
    name = "migration"
    description = "Migration assistant: deprecated and breaking changes"
    commands: list[str] = ["migrate"]

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
        sub = args[0].lower() if args else "check"
        if sub in ("check", ""):
            await self._cmd_check(context)
        else:
            await self._reply(context, "Usage: `/migrate check`")

    # ------------------------------------------------------------------ #

    async def _cmd_check(self, context: "CommandContext") -> None:
        if not self._app.config.ai_enabled:
            await self._reply(
                context, warning_msg("AI is disabled. Enable ai_enabled in config.")
            )
            return

        await self._reply(context, "⏳ Analyzing your HA installation\\.\\.\\.")

        # --- Gather context ---
        ha_version = "unknown"
        try:
            ha_cfg = await self._ha.get_config()
            ha_version = ha_cfg.get("version", "unknown") if isinstance(ha_cfg, dict) else "unknown"
        except Exception as exc:
            logger.warning("migration_ha_config_failed", error=str(exc))

        integrations_text = "Unavailable"
        try:
            entries = await self._ha.get_config_entries()
            domains = sorted({e.get("domain", "?") for e in entries[:_MAX_INTEGRATIONS]})
            integrations_text = ", ".join(domains) if domains else "None found"
        except Exception as exc:
            logger.warning("migration_entries_failed", error=str(exc))

        config_snippet = "Unavailable"
        if _CONFIG_FILE.exists():
            try:
                raw = _CONFIG_FILE.read_text(encoding="utf-8")
                config_snippet = raw[:_CONFIG_SNIPPET_CHARS]
                if len(raw) > _CONFIG_SNIPPET_CHARS:
                    config_snippet += "\n... (truncated)"
            except OSError:
                pass

        # --- Build prompt ---
        if _PROMPT_FILE.exists():
            prompt_template = _PROMPT_FILE.read_text()
        else:
            prompt_template = _FALLBACK_PROMPT

        prompt = (
            prompt_template
            .replace("{ha_version}", ha_version)
            .replace("{integrations}", integrations_text)
            .replace("{config_snippet}", config_snippet)
            .replace("{user_request}", "Check for deprecated integrations, obsolete YAML patterns, and upcoming breaking changes.")
        )

        # --- Call Claude ---
        try:
            ai = anthropic.AsyncAnthropic(api_key=self._app.config.anthropic_api_key)
            response = await ai.messages.create(
                model=self._app.config.ai_model,
                max_tokens=self._app.config.ai_max_tokens,
                messages=[{"role": "user", "content": prompt}],
            )
            analysis = response.content[0].text if response.content else "No analysis returned."
            logger.info(
                "migration_check_done",
                input_tokens=response.usage.input_tokens,
                output_tokens=response.usage.output_tokens,
            )
        except Exception as exc:
            await self._reply(context, error_msg(f"AI analysis failed: {exc}"))
            return

        # --- Format response ---
        header = bold(f"Migration Check — HA {escape_md(ha_version)}")
        # Escape the analysis for MarkdownV2
        body = escape_md(analysis)
        msg = f"{header}\n\n{body}"

        if len(msg) > 4000:
            msg = msg[:3990] + "\n_\\.\\.\\. truncated_"

        await context.update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN_V2)

    async def _reply(self, context: "CommandContext", text: str) -> None:
        await context.update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN_V2)


# Inline fallback if prompt file doesn't exist (e.g., running in dev)
_FALLBACK_PROMPT = """\
You are a Home Assistant migration advisor. Analyze this HA installation:

HA Version: {ha_version}
Integrations: {integrations}
Config snippet: {config_snippet}

{user_request}

Return a prioritized list (max 10 items) of deprecated patterns, breaking changes, and recommended actions.
Format each as: [CRITICAL/WARNING/INFO] Issue — Recommendation
"""
