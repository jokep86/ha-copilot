"""
Claude YAML generator for automations and scenes.
Handles: prompt loading, Claude call, fence stripping, YAML parse, Pydantic validation.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import TYPE_CHECKING, Any

import anthropic
from ruamel.yaml import YAML

from app.observability.logger import get_logger
from app.schemas.automation_schema import AutomationConfig
from app.schemas.scene_schema import SceneConfig

if TYPE_CHECKING:
    from app.config import AppConfig
    from app.ha.discovery import EntityDiscovery

logger = get_logger(__name__)

PROMPTS_DIR = Path("/app/prompts/v1")
_yaml = YAML()
_yaml.preserve_quotes = True


class YAMLGenerationError(Exception):
    pass


class YAMLGenerator:
    def __init__(
        self,
        config: "AppConfig",
        discovery: "EntityDiscovery",
    ) -> None:
        self._config = config
        self._discovery = discovery
        self._ai = anthropic.AsyncAnthropic(api_key=config.anthropic_api_key)

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #

    async def generate_automation(self, user_request: str) -> AutomationConfig:
        """Generate and validate an automation config from a NL description."""
        prompt_template = self._load_prompt("automation_creator.txt")
        entity_ctx = await self._entity_context()
        prompt = (
            prompt_template
            .replace("{entity_context}", entity_ctx)
            .replace("{user_request}", user_request)
        )
        raw = await self._call_claude(prompt)
        data = self._parse_yaml(raw)
        try:
            return AutomationConfig(**data)
        except Exception as exc:
            raise YAMLGenerationError(f"Automation schema validation failed: {exc}") from exc

    async def generate_scene(self, user_request: str) -> SceneConfig:
        """Generate and validate a scene config from a NL description."""
        prompt_template = self._load_prompt("scene_creator.txt")
        entity_ctx = await self._entity_context()
        prompt = (
            prompt_template
            .replace("{entity_context}", entity_ctx)
            .replace("{user_request}", user_request)
        )
        raw = await self._call_claude(prompt)
        data = self._parse_yaml(raw)
        try:
            return SceneConfig(**data)
        except Exception as exc:
            raise YAMLGenerationError(f"Scene schema validation failed: {exc}") from exc

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #

    def _load_prompt(self, filename: str) -> str:
        path = PROMPTS_DIR / filename
        if path.exists():
            return path.read_text()
        logger.warning("yaml_gen_prompt_missing", path=str(path))
        raise YAMLGenerationError(f"Prompt file not found: {path}")

    async def _entity_context(self) -> str:
        """Build a compact entity context string for the prompt."""
        try:
            domains = await self._discovery.get_domains()
            lines: list[str] = []
            for domain in list(domains.keys())[:8]:
                entities = await self._discovery.get_entities_by_domain(domain)
                for e in entities[:20]:
                    eid = e.get("entity_id", "")
                    fname = e.get("attributes", {}).get("friendly_name", eid)
                    state = e.get("state", "?")
                    lines.append(f"  {eid} ({fname}): {state}")
            return "\n".join(lines) or "No entities available."
        except Exception as exc:
            logger.warning("yaml_gen_context_failed", error=str(exc))
            return "Entity context unavailable."

    async def _call_claude(self, prompt: str) -> str:
        try:
            response = await self._ai.messages.create(
                model=self._config.ai_model,
                max_tokens=self._config.ai_max_tokens,
                messages=[{"role": "user", "content": prompt}],
            )
            text = response.content[0].text if response.content else ""
            logger.info(
                "yaml_gen_claude_done",
                input_tokens=response.usage.input_tokens,
                output_tokens=response.usage.output_tokens,
            )
            return text
        except Exception as exc:
            raise YAMLGenerationError(f"Claude call failed: {exc}") from exc

    def _parse_yaml(self, raw: str) -> dict[str, Any]:
        """Strip markdown fences and parse YAML → dict."""
        # Remove ```yaml ... ``` or ``` ... ``` fences
        cleaned = re.sub(r"^```(?:yaml)?\s*\n?", "", raw.strip(), flags=re.MULTILINE)
        cleaned = re.sub(r"\n?```\s*$", "", cleaned.strip(), flags=re.MULTILINE)
        cleaned = cleaned.strip()
        try:
            data = _yaml.load(cleaned)
        except Exception as exc:
            raise YAMLGenerationError(f"YAML parse error: {exc}\n\nRaw:\n{raw[:500]}") from exc
        if not isinstance(data, dict):
            raise YAMLGenerationError(f"Expected YAML dict, got {type(data).__name__}")
        return data
