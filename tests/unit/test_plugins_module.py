"""
Unit tests for PluginsModule.
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from app.modules.plugins_module import PluginsModule


def _make_module_mock(name="test_plugin", description="A test plugin", commands=None):
    mod = MagicMock()
    mod.name = name
    mod.description = description
    mod.commands = commands or [name]
    return mod


def _make_registry(modules=None):
    reg = MagicMock()
    reg.modules = modules or {}
    reg.register = MagicMock()
    reg.reload_plugin = AsyncMock()
    reg.reload_builtin = AsyncMock()
    return reg


def _make_app(registry=None):
    app = MagicMock()
    app.extra = {}
    if registry is not None:
        app.extra["registry"] = registry
    return app


def _make_context():
    ctx = MagicMock()
    ctx.update = MagicMock()
    ctx.update.message = MagicMock()
    ctx.update.message.reply_text = AsyncMock()
    ctx.user_id = 12345
    return ctx


class TestPluginsModule:
    async def test_setup_stores_app(self):
        mod = PluginsModule()
        app = _make_app()
        await mod.setup(app)
        assert mod._app is app

    async def test_teardown_is_noop(self):
        mod = PluginsModule()
        app = _make_app()
        await mod.setup(app)
        await mod.teardown()

    async def test_module_attributes(self):
        mod = PluginsModule()
        assert "plugins" in mod.commands
        assert "reload" in mod.commands
        assert mod.name == "plugins"

    async def test_cmd_list_no_registry(self):
        mod = PluginsModule()
        app = _make_app(registry=None)
        await mod.setup(app)
        ctx = _make_context()
        await mod.handle_command("plugins", [], ctx)
        text = ctx.update.message.reply_text.call_args[0][0]
        assert "Registry not available" in text

    async def test_cmd_list_shows_modules(self):
        registry = _make_registry(modules={
            "devices": _make_module_mock("devices", "Device control", ["devices", "status"]),
            "system": _make_module_mock("system", "System monitoring", ["sys"]),
        })
        mod = PluginsModule()
        app = _make_app(registry=registry)
        await mod.setup(app)
        ctx = _make_context()

        with patch("app.core.plugin_loader.PLUGINS_DIR", Path("/nonexistent")):
            await mod.handle_command("plugins", [], ctx)

        text = ctx.update.message.reply_text.call_args[0][0]
        assert "devices" in text
        assert "system" in text
        assert "2 modules total" in text

    async def test_cmd_load_dispatches(self):
        registry = _make_registry()
        mod = PluginsModule()
        app = _make_app(registry=registry)
        await mod.setup(app)
        ctx = _make_context()

        with patch("app.core.plugin_loader.PLUGINS_DIR", Path("/nonexistent")):
            await mod.handle_command("plugins", ["load"], ctx)

        text = ctx.update.message.reply_text.call_args[0][0]
        assert "does not exist" in text or "No new plugins" in text

    async def test_cmd_reload_no_name(self):
        mod = PluginsModule()
        app = _make_app()
        await mod.setup(app)
        ctx = _make_context()
        await mod.handle_command("reload", [], ctx)
        text = ctx.update.message.reply_text.call_args[0][0]
        assert "Usage" in text

    async def test_cmd_reload_no_registry(self):
        mod = PluginsModule()
        app = _make_app(registry=None)
        await mod.setup(app)
        ctx = _make_context()
        await mod.handle_command("reload", ["devices"], ctx)
        text = ctx.update.message.reply_text.call_args[0][0]
        assert "Registry not available" in text

    async def test_cmd_reload_module_not_found(self):
        registry = _make_registry(modules={})
        mod = PluginsModule()
        app = _make_app(registry=registry)
        await mod.setup(app)
        ctx = _make_context()
        await mod.handle_command("reload", ["nonexistent_module"], ctx)
        text = ctx.update.message.reply_text.call_args[0][0]
        assert "not registered" in text or "nonexistent_module" in text

    async def test_cmd_reload_community_plugin_success(self):
        registry = _make_registry(modules={
            "my_plugin": _make_module_mock("my_plugin"),
        })
        registry.reload_plugin = AsyncMock()  # success
        mod = PluginsModule()
        app = _make_app(registry=registry)
        await mod.setup(app)
        ctx = _make_context()
        await mod.handle_command("reload", ["my_plugin"], ctx)
        registry.reload_plugin.assert_awaited_once_with("my_plugin", app)
        text = ctx.update.message.reply_text.call_args[0][0]
        assert "reloaded" in text.lower()

    async def test_cmd_reload_falls_back_to_builtin(self):
        registry = _make_registry(modules={
            "devices": _make_module_mock("devices"),
        })
        registry.reload_plugin = AsyncMock(side_effect=FileNotFoundError("not a plugin file"))
        registry.reload_builtin = AsyncMock()
        mod = PluginsModule()
        app = _make_app(registry=registry)
        await mod.setup(app)
        ctx = _make_context()
        await mod.handle_command("reload", ["devices"], ctx)
        registry.reload_builtin.assert_awaited_once_with("devices", app)
        text = ctx.update.message.reply_text.call_args[0][0]
        assert "reloaded" in text.lower()

    async def test_cmd_reload_community_plugin_error(self):
        registry = _make_registry(modules={
            "bad_plugin": _make_module_mock("bad_plugin"),
        })
        registry.reload_plugin = AsyncMock(side_effect=Exception("import error"))
        mod = PluginsModule()
        app = _make_app(registry=registry)
        await mod.setup(app)
        ctx = _make_context()
        await mod.handle_command("reload", ["bad_plugin"], ctx)
        text = ctx.update.message.reply_text.call_args[0][0]
        assert "Reload failed" in text or "import error" in text

    async def test_cmd_reload_builtin_error(self):
        registry = _make_registry(modules={
            "devices": _make_module_mock("devices"),
        })
        registry.reload_plugin = AsyncMock(side_effect=FileNotFoundError)
        registry.reload_builtin = AsyncMock(side_effect=Exception("setup failed"))
        mod = PluginsModule()
        app = _make_app(registry=registry)
        await mod.setup(app)
        ctx = _make_context()
        await mod.handle_command("reload", ["devices"], ctx)
        text = ctx.update.message.reply_text.call_args[0][0]
        assert "Reload failed" in text or "setup failed" in text

    async def test_cmd_load_no_registry(self):
        mod = PluginsModule()
        app = _make_app(registry=None)
        await mod.setup(app)
        ctx = _make_context()
        await mod.handle_command("plugins", ["load"], ctx)
        text = ctx.update.message.reply_text.call_args[0][0]
        assert "Registry not available" in text
