"""
Abstract base class for all ha-copilot modules (see ADR-011).
Every module in app/modules/ implements this interface.
No auto-discovery — modules are registered explicitly in main.py.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.bot.handler import CommandContext
    from app.core.module_registry import AppContext


class ModuleBase(ABC):
    """
    Base class for all ha-copilot modules.

    Subclasses must set class-level attributes:
        name: str        — unique module identifier
        description: str — human-readable description
        commands: list   — Telegram commands this module handles (without /)
    """

    name: str = ""
    description: str = ""
    commands: list[str] = []

    @abstractmethod
    async def setup(self, app: "AppContext") -> None:
        """Initialize the module. Called once at startup before bot accepts messages."""
        ...

    @abstractmethod
    async def teardown(self) -> None:
        """Release resources. Called on graceful shutdown."""
        ...

    @abstractmethod
    async def handle_command(
        self,
        cmd: str,
        args: list[str],
        context: "CommandContext",
    ) -> None:
        """
        Handle a command dispatched by the bot.
        cmd:     command name (without /)
        args:    space-separated tokens after the command
        context: CommandContext with update, user_id, chat_id, trace_id
        """
        ...
