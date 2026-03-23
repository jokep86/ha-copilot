"""
Claude AI engine — NL interpreter with full production features:
- Progressive context loading (ADR-010)
- Conversation memory
- Fallback chain: retry → cache → alert
- Daily token budget enforcement
- AI Decision Audit Log
- Language auto-detection (Claude handles it natively)

Replaces the Phase 1 stub.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

import anthropic

from app.core.module_base import ModuleBase
from app.observability.logger import get_logger
from app.schemas.ai_action import AIAction, AIResponse, ActionType

if TYPE_CHECKING:
    from app.ai.audit import AIAuditLog
    from app.ai.context import ContextLoader
    from app.ai.conversation import ConversationMemory
    from app.bot.handler import CommandContext
    from app.config import AppConfig
    from app.core.module_registry import AppContext
    from app.database import Database

logger = get_logger(__name__)

PROMPTS_DIR = Path("/app/prompts")
PROMPT_VERSION = "v1"
RETRY_DELAYS = (2, 4)


class AIBudgetExceededError(Exception):
    pass


class AIServiceUnavailableError(Exception):
    pass


class AIParsingError(Exception):
    pass


class AIEngineModule(ModuleBase):
    """
    Handles free-text NL input via Claude.
    Registered for 'ai_nl' pseudo-command by BotHandler.
    """

    name = "ai_engine"
    description = "Claude AI natural language interpreter"
    commands: list[str] = ["ai_nl"]

    # Populated in setup()
    _config: "AppConfig"
    _db: "Database"
    _context: "ContextLoader"
    _conversation: "ConversationMemory"
    _audit: "AIAuditLog"
    _client: anthropic.AsyncAnthropic
    _system_prompt: str

    async def setup(self, app: "AppContext") -> None:
        from app.ai.audit import AIAuditLog
        from app.ai.context import ContextLoader
        from app.ai.conversation import ConversationMemory
        from app.ha.discovery import EntityDiscovery

        self._app = app
        self._config = app.config
        self._db = app.db
        self._client = anthropic.AsyncAnthropic(
            api_key=app.config.anthropic_api_key
        )

        # Discovery — injected via app.extra["discovery"]
        discovery: EntityDiscovery = app.extra.get("discovery")
        if not discovery:
            raise RuntimeError("AIEngineModule requires 'discovery' in AppContext.extra")

        self._context = ContextLoader(discovery)
        self._conversation = ConversationMemory(
            db=app.db,
            enabled=app.config.ai_conversation_memory,
            ttl_minutes=app.config.ai_conversation_ttl_minutes,
            max_messages=app.config.ai_conversation_max_messages,
        )
        self._audit = AIAuditLog(app.db)

        # Load system prompt
        prompt_path = PROMPTS_DIR / PROMPT_VERSION / "system.txt"
        if prompt_path.exists():
            self._system_prompt = prompt_path.read_text()
        else:
            logger.warning("system_prompt_not_found", path=str(prompt_path))
            self._system_prompt = (
                "You are a Home Assistant assistant. "
                "Respond with JSON {\"actions\": [...]} matching AIAction schema."
            )

        logger.info("ai_engine_loaded", prompt_version=PROMPT_VERSION)

    async def teardown(self) -> None:
        pass

    async def handle_command(
        self,
        cmd: str,
        args: list[str],
        context: "CommandContext",
    ) -> None:
        """Entry point for NL messages dispatched via CommandQueueManager."""
        text = " ".join(args)
        if not text.strip():
            return

        if not self._config.ai_enabled:
            if self._app.bot_send:
                await self._app.bot_send(
                    context.chat_id,
                    "🤖 AI is disabled\\. Set `ai_enabled: true` in the add\\-on config\\.",
                )
            return

        # Budget check
        try:
            await self._check_budget()
        except AIBudgetExceededError as exc:
            if self._app.bot_send:
                from app.bot.formatters import escape_md
                await self._app.bot_send(
                    context.chat_id,
                    f"🔴 {escape_md(str(exc))}",
                )
            return

        try:
            response = await self.process_nl(
                text=text,
                user_id=context.user_id,
                trace_id=context.trace_id,
            )
            # Store the AI response so mapper can execute it
            # The mapper is invoked via app.extra["mapper"]
            mapper = self._app.extra.get("mapper")
            if mapper:
                await mapper.execute(response, context)
            else:
                logger.warning("ai_mapper_not_registered")

        except AIServiceUnavailableError:
            if self._app.bot_send:
                await self._app.bot_send(
                    context.chat_id,
                    "🔴 AI unavailable\\. Use /help for structured commands\\.",
                )
        except Exception as exc:
            logger.error("ai_handle_command_error", error=str(exc), trace_id=context.trace_id)
            if self._app.bot_send:
                from app.bot.formatters import escape_md
                await self._app.bot_send(
                    context.chat_id,
                    f"🔴 Error: {escape_md(str(exc))}",
                )

    async def process_nl(
        self,
        text: str,
        user_id: int,
        trace_id: str = "",
    ) -> AIResponse:
        """
        Full NL → AIResponse pipeline:
        context loading → conversation history → Claude → parse → audit.
        """
        start_ms = int(time.monotonic() * 1000)

        # Build system prompt with entity context
        entity_context = await self._context.get_prompt_context(
            query=text,
            entity_aliases=self._config.entity_aliases,
        )
        conversation_history = await self._conversation.get_history(user_id)
        conv_text = "\n".join(
            f"{m['role'].upper()}: {m['content']}" for m in conversation_history
        )

        system = self._system_prompt.replace("{entity_context}", entity_context)
        system = system.replace("{conversation_history}", conv_text or "No previous context.")
        system = system.replace(
            "{entity_aliases}",
            json.dumps(self._config.entity_aliases) if self._config.entity_aliases else "None",
        )

        messages = [{"role": "user", "content": text}]

        # Fallback chain: call → retry → retry → cache → error
        response = await self._call_with_fallback(
            system=system,
            messages=messages,
            text=text,
            trace_id=trace_id,
        )

        # Store in conversation memory
        await self._conversation.add(user_id, "user", text, trace_id)
        await self._conversation.add(user_id, "assistant", response.raw_response, trace_id)

        # Audit log
        latency_ms = int(time.monotonic() * 1000) - start_ms
        await self._audit.log(
            response=response,
            user_id=user_id,
            raw_prompt=f"SYSTEM: {system}\n\nUSER: {text}",
            latency_ms=latency_ms,
        )

        return response

    async def _call_with_fallback(
        self,
        system: str,
        messages: list[dict],
        text: str,
        trace_id: str,
    ) -> AIResponse:
        """Call Claude with retry → cache fallback chain."""
        last_exc: Exception | None = None

        for attempt, delay in enumerate((*RETRY_DELAYS, None), start=1):
            try:
                return await self._call_claude(system, messages, trace_id)
            except anthropic.RateLimitError as exc:
                last_exc = exc
                logger.warning("ai_rate_limit", attempt=attempt)
            except anthropic.APIError as exc:
                last_exc = exc
                logger.warning("ai_api_error", attempt=attempt, error=str(exc))
            except AIParsingError as exc:
                last_exc = exc
                logger.warning("ai_parse_error", attempt=attempt, error=str(exc))

            if delay is not None:
                await asyncio.sleep(delay)

        # All retries failed — check cache
        cached = await self._get_cache(text)
        if cached:
            logger.warning("ai_using_cached_response", text_preview=text[:50])
            cached.from_cache = True
            return cached

        raise AIServiceUnavailableError(
            f"AI unavailable after {len(RETRY_DELAYS)} retries: {last_exc}"
        )

    async def _call_claude(
        self,
        system: str,
        messages: list[dict],
        trace_id: str,
    ) -> AIResponse:
        """Single Claude API call. Parses response to AIResponse."""
        response = await self._client.messages.create(
            model=self._config.ai_model,
            max_tokens=self._config.ai_max_tokens,
            system=system,
            messages=messages,
        )

        raw = response.content[0].text if response.content else ""
        actions = self._parse_response(raw, trace_id)

        ai_response = AIResponse(
            actions=actions,
            raw_response=raw,
            prompt_version=PROMPT_VERSION,
            model=response.model,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            trace_id=trace_id,
        )

        # Cache successful response
        await self._set_cache(
            text=" ".join(m.get("content", "") for m in messages),
            response=ai_response,
        )

        return ai_response

    def _parse_response(self, raw: str, trace_id: str) -> list[AIAction]:
        """Parse Claude's JSON response into AIAction list."""
        # Strip markdown code fences if present
        text = raw.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            text = "\n".join(lines[1:-1]) if len(lines) > 2 else text

        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            raise AIParsingError(f"JSON parse failed: {exc}. Raw: {raw[:200]}")

        raw_actions = data.get("actions", [])
        if not raw_actions:
            # Treat as unknown action
            return [AIAction(action_type=ActionType.UNKNOWN, message=raw[:500])]

        actions: list[AIAction] = []
        for a in raw_actions:
            try:
                actions.append(AIAction.model_validate(a))
            except Exception as exc:
                logger.warning("ai_action_validation_failed", error=str(exc))

        return actions or [AIAction(action_type=ActionType.UNKNOWN)]

    async def _check_budget(self) -> None:
        """Raise AIBudgetExceededError if daily token budget is exhausted."""
        used = await self._audit.get_daily_tokens_used()
        budget = self._config.ai_daily_token_budget
        if used >= budget:
            raise AIBudgetExceededError(
                f"Daily token budget exhausted ({used:,}/{budget:,}). "
                f"Reset at midnight UTC."
            )
        if used >= budget * 0.8:
            logger.warning(
                "ai_budget_80pct",
                used=used,
                budget=budget,
                pct=int(used / budget * 100),
            )

    # ------------------------------------------------------------------ #
    # Simple query cache
    # ------------------------------------------------------------------ #

    async def _cache_key(self, text: str) -> str:
        return hashlib.sha256(text.lower().strip().encode()).hexdigest()

    async def _get_cache(self, text: str) -> AIResponse | None:
        key = await self._cache_key(text)
        cursor = await self._db.conn.execute(
            """
            SELECT response FROM ai_cache
            WHERE query_hash = ?
              AND datetime(created_at, '+' || ttl_seconds || ' seconds') > datetime('now')
            """,
            (key,),
        )
        row = await cursor.fetchone()
        if not row:
            return None
        try:
            data = json.loads(row[0])
            return AIResponse.model_validate(data)
        except Exception:
            return None

    async def _set_cache(self, text: str, response: AIResponse) -> None:
        key = await self._cache_key(text)
        value = response.model_dump_json()
        await self._db.conn.execute(
            """
            INSERT OR REPLACE INTO ai_cache (query_hash, query_text, response, ttl_seconds)
            VALUES (?, ?, ?, 300)
            """,
            (key, text[:500], value),
        )
        await self._db.conn.commit()
