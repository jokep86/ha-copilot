"""
Explicit module registration and lifecycle management (see ADR-011).
No auto-discovery. No plugin framework. Modules registered in main.py.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, Coroutine, Optional

from app.core.module_base import ModuleBase
from app.observability.logger import get_logger

if TYPE_CHECKING:
    from app.config import AppConfig
    from app.database import Database
    from app.ha.client import HAClient
    from app.ha.supervisor import SupervisorClient

logger = get_logger(__name__)


@dataclass
class AppContext:
    """Shared context passed to all modules during setup."""

    config: "AppConfig"
    db: "Database"
    ha_client: "HAClient"
    supervisor_client: "SupervisorClient"
    # Callable: (chat_id: int, text: str) -> Coroutine — set after bot is up
    bot_send: Optional[Callable[[int, str], Coroutine]] = None
    extra: dict[str, Any] = field(default_factory=dict)


class ModuleRegistry:
    """Manages module lifecycle: register → setup → teardown."""

    def __init__(self) -> None:
        self._modules: dict[str, ModuleBase] = {}
        self._command_map: dict[str, ModuleBase] = {}

    def register(self, module: ModuleBase) -> None:
        """Register a module. Raises ValueError on duplicate name or command."""
        if not module.name:
            raise ValueError(f"Module {type(module).__name__} has no name")
        if module.name in self._modules:
            raise ValueError(f"Module '{module.name}' already registered")
        for cmd in module.commands:
            if cmd in self._command_map:
                raise ValueError(
                    f"Command '{cmd}' already registered by '{self._command_map[cmd].name}'"
                )
        self._modules[module.name] = module
        for cmd in module.commands:
            self._command_map[cmd] = module
        logger.debug("module_registered", name=module.name, commands=module.commands)

    async def setup_all(self, app: AppContext) -> None:
        """Call setup() on all modules. Raises on first failure."""
        for name, module in self._modules.items():
            try:
                await module.setup(app)
                logger.info("module_setup_ok", name=name)
            except Exception as exc:
                logger.error("module_setup_failed", name=name, error=str(exc))
                raise

    async def teardown_all(self) -> None:
        """Call teardown() in reverse registration order. Logs but does not raise."""
        for name, module in reversed(list(self._modules.items())):
            try:
                await module.teardown()
                logger.info("module_teardown_ok", name=name)
            except Exception as exc:
                logger.warning("module_teardown_failed", name=name, error=str(exc))

    def get_module_for_command(self, cmd: str) -> Optional[ModuleBase]:
        """Return the module that handles cmd (without /), or None."""
        return self._command_map.get(cmd.lstrip("/"))

    def unregister(self, name: str) -> ModuleBase:
        """
        Remove a module from the registry by name.
        Does NOT call teardown — caller is responsible.
        Raises KeyError if not found.
        """
        module = self._modules.pop(name)
        for cmd in module.commands:
            self._command_map.pop(cmd, None)
        logger.debug("module_unregistered", name=name)
        return module

    async def reload_plugin(
        self, name: str, app: "AppContext", plugins_dir: Path | None = None
    ) -> None:
        """
        Hot-reload a plugin module by name.
        1. Teardown + unregister the existing instance.
        2. Re-import the plugin file from plugins_dir (default: PLUGINS_DIR).
        3. Register + setup the new instance.
        Only works for modules loaded from the plugin directory.
        """
        from app.core.plugin_loader import PLUGINS_DIR, load_plugin_file

        pdir = plugins_dir if plugins_dir else PLUGINS_DIR

        if name not in self._modules:
            raise KeyError(f"Module '{name}' not registered")

        # Find the plugin file — convention: module name matches filename stem
        plugin_path = pdir / f"{name}.py"
        if not plugin_path.exists():
            # Also try underscore → hyphen and vice-versa
            candidates = list(pdir.glob("*.py"))
            matches = [p for p in candidates if p.stem.replace("-", "_") == name.replace("-", "_")]
            if not matches:
                raise FileNotFoundError(f"Plugin file not found for module '{name}' in {pdir}")
            plugin_path = matches[0]

        # Teardown existing
        existing = self._modules[name]
        try:
            await existing.teardown()
        except Exception as exc:
            logger.warning("reload_teardown_failed", name=name, error=str(exc))

        self.unregister(name)

        # Re-load from file
        cls = load_plugin_file(plugin_path)
        new_instance = cls()
        self.register(new_instance)
        await new_instance.setup(app)
        logger.info("plugin_reloaded", name=name, file=plugin_path.name)

    @property
    def modules(self) -> dict[str, ModuleBase]:
        return dict(self._modules)

    @property
    def command_map(self) -> dict[str, ModuleBase]:
        return dict(self._command_map)
