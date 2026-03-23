"""
NL scheduled commands via HA automations — Phase 4 stub.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from app.core.module_base import ModuleBase
from app.observability.logger import get_logger

if TYPE_CHECKING:
    from app.bot.handler import CommandContext
    from app.core.module_registry import AppContext

logger = get_logger(__name__)


class SchedulerModule(ModuleBase):
    """NL time-based commands converted to one-shot HA automations. Stub — full implementation in Phase 4."""

    name = "scheduler"
    description = "NL scheduled commands via HA automations"
    commands: list[str] = ["schedule"]

    async def setup(self, app: "AppContext") -> None:
        self._app = app

    async def teardown(self) -> None:
        pass

    async def handle_command(
        self,
        cmd: str,
        args: list[str],
        context: "CommandContext",
    ) -> None:
        logger.info("scheduler_stub_called", cmd=cmd, user_id=context.user_id)
        if self._app.bot_send:
            await self._app.bot_send(
                context.chat_id,
                f"/{cmd} coming in Phase 4\\. Use /help for available commands\\.",
            )
