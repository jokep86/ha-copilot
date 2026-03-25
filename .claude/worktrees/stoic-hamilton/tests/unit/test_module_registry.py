"""
Unit tests for ModuleRegistry.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core.module_base import ModuleBase
from app.core.module_registry import AppContext, ModuleRegistry


class _FakeModule(ModuleBase):
    name = "fake"
    description = "Fake module for testing"
    commands: list[str] = ["fake_cmd", "another_cmd"]

    async def setup(self, app: AppContext) -> None:
        self.app = app

    async def teardown(self) -> None:
        pass

    async def handle_command(self, cmd, args, context) -> None:
        pass


class _AnotherModule(ModuleBase):
    name = "other"
    description = "Another module"
    commands: list[str] = ["other_cmd"]

    async def setup(self, app: AppContext) -> None:
        pass

    async def teardown(self) -> None:
        pass

    async def handle_command(self, cmd, args, context) -> None:
        pass


@pytest.fixture
def registry() -> ModuleRegistry:
    return ModuleRegistry()


def test_register_module(registry: ModuleRegistry) -> None:
    registry.register(_FakeModule())
    assert "fake" in registry.modules


def test_register_duplicate_name_raises(registry: ModuleRegistry) -> None:
    registry.register(_FakeModule())
    with pytest.raises(ValueError, match="already registered"):
        registry.register(_FakeModule())


def test_register_duplicate_command_raises(registry: ModuleRegistry) -> None:
    registry.register(_FakeModule())

    class _Conflict(ModuleBase):
        name = "conflict"
        description = ""
        commands: list[str] = ["fake_cmd"]  # same command

        async def setup(self, app): pass
        async def teardown(self): pass
        async def handle_command(self, cmd, args, ctx): pass

    with pytest.raises(ValueError, match="already registered"):
        registry.register(_Conflict())


def test_get_module_for_command(registry: ModuleRegistry) -> None:
    registry.register(_FakeModule())
    module = registry.get_module_for_command("fake_cmd")
    assert module is not None
    assert module.name == "fake"


def test_get_module_for_unknown_command(registry: ModuleRegistry) -> None:
    assert registry.get_module_for_command("nonexistent") is None


def test_get_module_strips_slash(registry: ModuleRegistry) -> None:
    registry.register(_FakeModule())
    assert registry.get_module_for_command("/fake_cmd") is not None


@pytest.mark.asyncio
async def test_setup_all_calls_module_setup(registry: ModuleRegistry) -> None:
    module = _FakeModule()
    registry.register(module)
    app_ctx = MagicMock(spec=AppContext)
    await registry.setup_all(app_ctx)
    assert hasattr(module, "app")


@pytest.mark.asyncio
async def test_teardown_all_does_not_raise(registry: ModuleRegistry) -> None:
    registry.register(_FakeModule())
    registry.register(_AnotherModule())
    app_ctx = MagicMock(spec=AppContext)
    await registry.setup_all(app_ctx)
    await registry.teardown_all()  # should not raise


@pytest.mark.asyncio
async def test_setup_failure_propagates(registry: ModuleRegistry) -> None:
    class _BrokenModule(ModuleBase):
        name = "broken"
        description = ""
        commands: list[str] = []

        async def setup(self, app):
            raise RuntimeError("setup failed")

        async def teardown(self): pass
        async def handle_command(self, cmd, args, ctx): pass

    registry.register(_BrokenModule())
    with pytest.raises(RuntimeError, match="setup failed"):
        await registry.setup_all(MagicMock(spec=AppContext))


def test_modules_property_returns_copy(registry: ModuleRegistry) -> None:
    registry.register(_FakeModule())
    modules = registry.modules
    modules["injected"] = MagicMock()  # mutate the copy
    assert "injected" not in registry.modules
