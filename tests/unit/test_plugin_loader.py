"""
Unit tests for the plugin loader and hot-reload system.
"""
from __future__ import annotations

import textwrap
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.plugin_loader import (
    PluginLoadError,
    _find_module_class,
    load_plugin_file,
    load_all_plugins,
)
from app.core.module_base import ModuleBase
from app.core.module_registry import ModuleRegistry


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_plugin(tmp_path: Path, filename: str, content: str) -> Path:
    p = tmp_path / filename
    p.write_text(textwrap.dedent(content))
    return p


def _valid_plugin_code(name: str = "my_plugin", commands: list[str] | None = None) -> str:
    cmds = commands or ["myplugin"]
    return f"""
from app.core.module_base import ModuleBase

class MyPlugin(ModuleBase):
    name = "{name}"
    description = "test plugin"
    commands = {cmds!r}

    async def setup(self, app):
        pass

    async def teardown(self):
        pass

    async def handle_command(self, cmd, args, context):
        pass
"""


# ---------------------------------------------------------------------------
# load_plugin_file
# ---------------------------------------------------------------------------

class TestLoadPluginFile:
    def test_loads_valid_plugin(self, tmp_path):
        path = _write_plugin(tmp_path, "my_plugin.py", _valid_plugin_code())
        cls = load_plugin_file(path)
        assert issubclass(cls, ModuleBase)
        assert cls.name == "my_plugin"

    def test_raises_when_no_modulebase_subclass(self, tmp_path):
        path = _write_plugin(tmp_path, "bad.py", "x = 1\n")
        with pytest.raises(PluginLoadError, match="ModuleBase subclass"):
            load_plugin_file(path)

    def test_raises_when_class_has_no_name(self, tmp_path):
        code = """
from app.core.module_base import ModuleBase

class Unnamed(ModuleBase):
    name = ""
    description = ""
    commands = []
    async def setup(self, app): pass
    async def teardown(self): pass
    async def handle_command(self, cmd, args, ctx): pass
"""
        path = _write_plugin(tmp_path, "unnamed.py", code)
        with pytest.raises(PluginLoadError, match="non-empty `name`"):
            load_plugin_file(path)

    def test_raises_on_syntax_error(self, tmp_path):
        path = _write_plugin(tmp_path, "broken.py", "def bad syntax(:\n")
        with pytest.raises(PluginLoadError, match="Error executing plugin"):
            load_plugin_file(path)

    def test_raises_on_import_error(self, tmp_path):
        code = "from nonexistent_module_xyz import something\n"
        path = _write_plugin(tmp_path, "import_err.py", code)
        with pytest.raises(PluginLoadError, match="Error executing plugin"):
            load_plugin_file(path)


# ---------------------------------------------------------------------------
# load_all_plugins
# ---------------------------------------------------------------------------

class TestLoadAllPlugins:
    def test_returns_empty_when_dir_missing(self):
        registry = ModuleRegistry()
        with patch("app.core.plugin_loader.PLUGINS_DIR", Path("/nonexistent/dir")):
            result = load_all_plugins(registry)
        assert result == []

    def test_loads_valid_plugin_file(self, tmp_path):
        _write_plugin(tmp_path, "my_plugin.py", _valid_plugin_code("my_plugin", ["myplugin"]))
        registry = ModuleRegistry()
        with patch("app.core.plugin_loader.PLUGINS_DIR", tmp_path):
            result = load_all_plugins(registry)
        assert "my_plugin" in result
        assert "my_plugin" in registry.modules

    def test_skips_broken_plugin_continues_loading_others(self, tmp_path):
        _write_plugin(tmp_path, "broken.py", "def bad syntax(:\n")
        _write_plugin(tmp_path, "good_plugin.py", _valid_plugin_code("good_plugin", ["good"]))
        registry = ModuleRegistry()
        with patch("app.core.plugin_loader.PLUGINS_DIR", tmp_path):
            result = load_all_plugins(registry)
        assert "good_plugin" in result
        assert "good_plugin" in registry.modules

    def test_skips_duplicate_command(self, tmp_path):
        # Two plugins claiming the same command — second should fail to register
        _write_plugin(tmp_path, "a.py", _valid_plugin_code("plugin_a", ["dupe"]))
        _write_plugin(tmp_path, "b.py", _valid_plugin_code("plugin_b", ["dupe"]))
        registry = ModuleRegistry()
        with patch("app.core.plugin_loader.PLUGINS_DIR", tmp_path):
            result = load_all_plugins(registry)
        # Only one of them should be loaded (first alphabetically wins)
        assert len([r for r in result if r in ("plugin_a", "plugin_b")]) == 1

    def test_loads_multiple_plugins(self, tmp_path):
        _write_plugin(tmp_path, "a.py", _valid_plugin_code("plugin_a", ["cmda"]))
        _write_plugin(tmp_path, "b.py", _valid_plugin_code("plugin_b", ["cmdb"]))
        registry = ModuleRegistry()
        with patch("app.core.plugin_loader.PLUGINS_DIR", tmp_path):
            result = load_all_plugins(registry)
        assert "plugin_a" in result
        assert "plugin_b" in result


# ---------------------------------------------------------------------------
# ModuleRegistry.unregister
# ---------------------------------------------------------------------------

class TestModuleRegistryUnregister:
    def _make_module(self, name: str, commands: list[str]) -> ModuleBase:
        m = MagicMock(spec=ModuleBase)
        m.name = name
        m.commands = commands
        return m

    def test_unregister_removes_module_and_commands(self):
        registry = ModuleRegistry()
        mod = self._make_module("test_mod", ["testcmd"])
        registry.register(mod)
        assert "test_mod" in registry.modules

        returned = registry.unregister("test_mod")
        assert returned is mod
        assert "test_mod" not in registry.modules
        assert "testcmd" not in registry.command_map

    def test_unregister_raises_on_unknown(self):
        registry = ModuleRegistry()
        with pytest.raises(KeyError):
            registry.unregister("nonexistent")


# ---------------------------------------------------------------------------
# ModuleRegistry.reload_plugin
# ---------------------------------------------------------------------------

class TestReloadPlugin:
    async def test_reloads_plugin_from_file(self, tmp_path):
        # Write initial plugin
        path = _write_plugin(tmp_path, "my_plugin.py", _valid_plugin_code("my_plugin", ["myplugin"]))

        registry = ModuleRegistry()
        with patch("app.core.plugin_loader.PLUGINS_DIR", tmp_path):
            load_all_plugins(registry)

        assert "my_plugin" in registry.modules
        original = registry.modules["my_plugin"]

        # Reload — should teardown old, load fresh from file
        app_ctx = MagicMock()
        app_ctx.config = MagicMock()

        with patch("app.core.plugin_loader.PLUGINS_DIR", tmp_path):
            await registry.reload_plugin("my_plugin", app_ctx, plugins_dir=tmp_path)

        assert "my_plugin" in registry.modules
        # New instance was created
        new_inst = registry.modules["my_plugin"]
        assert new_inst is not original

    async def test_raises_when_module_not_registered(self, tmp_path):
        registry = ModuleRegistry()
        app_ctx = MagicMock()
        with pytest.raises(KeyError, match="not registered"):
            await registry.reload_plugin("nonexistent", app_ctx, plugins_dir=tmp_path)

    async def test_raises_when_plugin_file_not_found(self, tmp_path):
        # Register a mock module (simulating a built-in)
        registry = ModuleRegistry()
        mod = MagicMock(spec=ModuleBase)
        mod.name = "builtin_mod"
        mod.commands = ["builtin"]
        mod.teardown = AsyncMock()
        registry.register(mod)

        app_ctx = MagicMock()
        # tmp_path has no file for "builtin_mod"
        with pytest.raises(FileNotFoundError):
            await registry.reload_plugin("builtin_mod", app_ctx, plugins_dir=tmp_path)

        # Original module should still be registered after failed reload
        assert "builtin_mod" in registry.modules


# ---------------------------------------------------------------------------
# ModuleRegistry.reload_builtin
# ---------------------------------------------------------------------------

class TestReloadBuiltin:
    def _make_real_module_class(self, name: str, commands: list[str]):
        """Create a concrete ModuleBase subclass (not a Mock) so type(instance) works."""
        from app.core.module_base import ModuleBase as _MB

        _name = name
        _commands = commands

        class _Mod(_MB):
            name = _name
            description = "test"
            commands = _commands

            async def setup(self, app): pass
            async def teardown(self): pass
            async def handle_command(self, cmd, args, context): pass

        return _Mod

    async def test_reloads_builtin_with_fresh_instance(self):
        registry = ModuleRegistry()
        cls = self._make_real_module_class("builtin_a", ["bcmd"])
        original = cls()
        registry.register(original)

        app_ctx = MagicMock()
        await registry.reload_builtin("builtin_a", app_ctx)

        assert "builtin_a" in registry.modules
        new_inst = registry.modules["builtin_a"]
        assert new_inst is not original
        assert isinstance(new_inst, cls)

    async def test_new_instance_has_setup_called(self):
        registry = ModuleRegistry()
        cls = self._make_real_module_class("builtin_b", ["bcmd2"])
        registry.register(cls())

        app_ctx = MagicMock()
        setup_calls = []

        # Patch setup on the class so all new instances are tracked
        original_setup = cls.setup
        async def _tracked_setup(self, app):
            setup_calls.append(app)
        cls.setup = _tracked_setup

        await registry.reload_builtin("builtin_b", app_ctx)

        cls.setup = original_setup  # restore
        assert len(setup_calls) == 1
        assert setup_calls[0] is app_ctx

    async def test_original_teardown_called(self):
        registry = ModuleRegistry()
        cls = self._make_real_module_class("builtin_c", ["bcmd3"])
        original = cls()
        teardown_called = []

        async def _tracked_teardown(self):
            teardown_called.append(True)
        original.teardown = lambda: _tracked_teardown(original)  # type: ignore

        # Use AsyncMock directly on the instance
        original.teardown = AsyncMock()
        registry.register(original)

        app_ctx = MagicMock()
        await registry.reload_builtin("builtin_c", app_ctx)

        original.teardown.assert_called_once()

    async def test_raises_when_not_registered(self):
        registry = ModuleRegistry()
        with pytest.raises(KeyError, match="not registered"):
            await registry.reload_builtin("nonexistent", MagicMock())

    async def test_tolerates_teardown_failure(self):
        """Reload continues even if teardown raises."""
        registry = ModuleRegistry()
        cls = self._make_real_module_class("builtin_d", ["bcmd4"])
        original = cls()
        original.teardown = AsyncMock(side_effect=Exception("teardown error"))  # type: ignore
        registry.register(original)

        app_ctx = MagicMock()
        # Should not raise
        await registry.reload_builtin("builtin_d", app_ctx)
        assert "builtin_d" in registry.modules
