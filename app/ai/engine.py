"""
Claude AI engine — NL interpreter, token tracking, fallback chain.
Phase 1: stub. Full implementation (progressive context loading,
conversation memory, audit log, budget) in Phase 2.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from app.core.module_base import ModuleBase
from app.observability.logger import get_logger

if TYPE_CHECKING:
    from app.bot.handler import CommandContext
    from app.core.module_registry import AppContext

logger = get_logger(__name__)


class AIEngineModule(ModuleBase):
    """Handles free-text NL input via Claude. Stub for Phase 1."""

    name = "ai_engine"
    description = "Claude AI natural language interpreter"
    commands = ["ai_nl"]

    async def setup(self, app: "AppContext") -> None:
        self._app = app
        logger.info("ai_engine_stub_loaded", note="full_implementation_in_phase2")

    async def teardown(self) -> None:
        pass

    async def handle_command(
        self,
        cmd: str,
        args: list[str],
        context: "CommandContext",
    ) -> None:
        text = " ".join(args)
        logger.info(
            "ai_nl_stub",
            user_id=context.user_id,
            text_preview=text[:80],
        )
        if self._app.bot_send:
            await self._app.bot_send(
                context.chat_id,
                "🤖 AI engine coming in Phase 2\\. Use /help for available commands\\.",
            )
