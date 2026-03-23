"""
configuration.yaml and integrations management — Phase 6 stub.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from app.core.module_base import ModuleBase
from app.observability.logger import get_logger

if TYPE_CHECKING:
    from app.bot.handler import CommandContext
    from app.core.module_registry import AppContext

logger = get_logger(__name__)


class ConfigManagerModule(ModuleBase):
    """configuration.yaml editing, integrations, and user management. Stub — full implementation in Phase 6."""

    name = "config_manager"
    description = "configuration.yaml and integrations"
    commands: list[str] = ["config", "integrations", "users"]

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
        logger.info("config_manager_stub_called", cmd=cmd, user_id=context.user_id)
        if self._app.bot_send:
            await self._app.bot_send(
                context.chat_id,
                f"/{cmd} coming in Phase 6\\. Use /help for available commands\\.",
            )
