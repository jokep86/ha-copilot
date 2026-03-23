"""
AI documentation for automations, entities, and integrations — Phase 4.

/explain auto <id_or_alias>      — explain an automation in natural language
/explain entity <entity_id>      — explain an entity (source, usage, automations)
/explain integration <name>      — explain a HA integration
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

import anthropic
from telegram.constants import ParseMode

from app.bot.formatters import bold, code, error_msg, escape_md
from app.core.module_base import ModuleBase
from app.observability.logger import get_logger

if TYPE_CHECKING:
    from app.bot.handler import CommandContext
    from app.core.module_registry import AppContext

logger = get_logger(__name__)

PROMPT_PATH = Path("/app/prompts/v1/explainer.txt")
MAX_OBJECT_CHARS = 4000


class ExplainModule(ModuleBase):
    name = "explain"
    description = "AI documentation for entities and automations"
    commands: list[str] = ["explain"]

    async def setup(self, app: "AppContext") -> None:
        self._app = app
        self._ha = app.ha_client
        self._ai = anthropic.AsyncAnthropic(api_key=app.config.anthropic_api_key)

        if PROMPT_PATH.exists():
            self._prompt = PROMPT_PATH.read_text()
        else:
            logger.warning("explainer_prompt_missing", path=str(PROMPT_PATH))
            self._prompt = (
                "Explain this Home Assistant {object_type} called {object_id} "
                "in plain language.\n\nData:\n{object_data}"
            )

    async def teardown(self) -> None:
        pass

    async def handle_command(
        self, cmd: str, args: list[str], context: "CommandContext"
    ) -> None:
        if len(args) < 2:
            await self._reply(
                context,
                bold("Explain") + "\n"
                "Usage:\n"
                "`/explain auto \\<id\\_or\\_alias\\>`\n"
                "`/explain entity \\<entity\\_id\\>`\n"
                "`/explain integration \\<name\\>`",
            )
            return

        object_type = args[0].lower()
        object_id = " ".join(args[1:])

        if object_type in ("auto", "automation"):
            await self._explain_automation(object_id, context)
        elif object_type == "entity":
            await self._explain_entity(object_id, context)
        elif object_type in ("integration", "int"):
            await self._explain_integration(object_id, context)
        else:
            await self._reply(
                context,
                f"Unknown type {code(object_type)}\\. Use: auto, entity, integration",
            )

    # ------------------------------------------------------------------ #

    async def _explain_automation(self, query: str, context: "CommandContext") -> None:
        try:
            autos = await self._ha.get_automations()
        except Exception as exc:
            await self._reply(context, error_msg(f"Cannot get automations: {exc}"))
            return

        q = query.lower()
        found = None
        for a in autos:
            if a.get("id", "").lower() == q or q in a.get("alias", "").lower():
                found = a
                break

        if not found:
            await self._reply(context, escape_md(f"No automation matching '{query}'."))
            return

        await self._reply(context, f"🤖 Explaining automation…")
        object_data = json.dumps(found, indent=2, ensure_ascii=False)[:MAX_OBJECT_CHARS]
        await self._ask_claude("automation", found.get("alias", query), object_data, context)

    async def _explain_entity(self, entity_id: str, context: "CommandContext") -> None:
        try:
            state = await self._ha.get_state(entity_id)
        except Exception as exc:
            await self._reply(context, error_msg(f"Cannot get entity state: {exc}"))
            return

        await self._reply(context, f"🤖 Explaining entity…")
        object_data = json.dumps(state, indent=2, ensure_ascii=False)[:MAX_OBJECT_CHARS]
        await self._ask_claude("entity", entity_id, object_data, context)

    async def _explain_integration(self, name: str, context: "CommandContext") -> None:
        # For integrations, pass the name + any entities that look like they belong to it
        extra = ""
        try:
            discovery = self._app.extra.get("discovery")
            if discovery:
                # Heuristic: entities whose entity_id contains the integration name
                all_states = await discovery.get_all_states()
                related = [
                    e for e in all_states
                    if name.lower() in e.get("entity_id", "").lower()
                ][:10]
                if related:
                    extra = "\n\nRelated entities:\n" + "\n".join(
                        f"  {e['entity_id']}: {e.get('state', '?')}" for e in related
                    )
        except Exception:
            pass

        await self._reply(context, f"🤖 Explaining integration…")
        object_data = f"Integration name: {name}{extra}"
        await self._ask_claude("integration", name, object_data, context)

    async def _ask_claude(
        self,
        object_type: str,
        object_id: str,
        object_data: str,
        context: "CommandContext",
    ) -> None:
        if not self._app.config.ai_enabled:
            await self._reply(context, "AI is disabled\\. Enable `ai_enabled` to use /explain\\.")
            return

        prompt = (
            self._prompt
            .replace("{object_type}", object_type)
            .replace("{object_id}", object_id)
            .replace("{object_data}", object_data)
        )

        try:
            response = await self._ai.messages.create(
                model=self._app.config.ai_model,
                max_tokens=self._app.config.ai_max_tokens,
                messages=[{"role": "user", "content": prompt}],
            )
            explanation = response.content[0].text if response.content else "No explanation available."
            logger.info(
                "explain_done",
                object_type=object_type,
                object_id=object_id,
                input_tokens=response.usage.input_tokens,
                output_tokens=response.usage.output_tokens,
            )
        except Exception as exc:
            logger.error("explain_claude_failed", error=str(exc))
            await self._reply(context, error_msg(f"AI explanation failed: {exc}"))
            return

        header = f"{bold('Explanation')} — {code(escape_md(object_id))}"
        await context.update.message.reply_text(
            f"{header}\n\n{escape_md(explanation)}",
            parse_mode=ParseMode.MARKDOWN_V2,
        )

    async def _reply(self, context: "CommandContext", text: str) -> None:
        await context.update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN_V2)
