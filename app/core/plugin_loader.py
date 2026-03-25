"""
Dynamic plugin loader — Fase 2 (see ADR-011).

Scans /data/plugins/ for Python files that export a ModuleBase subclass.
Each .py file is loaded in isolation; failures are logged but do not block startup.

Plugin contract:
  - The file must define exactly one class that subclasses ModuleBase
    (with a non-empty `name` attribute).
  - That class is instantiated with no arguments and registered.
  - Built-in modules have priority: if a plugin tries to claim a command
    already registered by a built-in, it is rejected with a clear log message.
"""
from __future__ import annotations

import importlib.util
import inspect
import sys
from pathlib import Path
from typing import TYPE_CHECKING

from app.core.module_base import ModuleBase
from app.observability.logger import get_logger

if TYPE_CHECKING:
    from app.core.module_registry import ModuleRegistry

logger = get_logger(__name__)

PLUGINS_DIR = Path("/data/plugins")


class PluginLoadError(Exception):
    pass


def _find_module_class(module_obj: object) -> type[ModuleBase] | None:
    """Return the first concrete ModuleBase subclass defined in the file, or None."""
    for _name, obj in inspect.getmembers(module_obj, inspect.isclass):
        if (
            obj is not ModuleBase
            and issubclass(obj, ModuleBase)
            and obj.__module__ == getattr(module_obj, "__name__", None)
            and obj.name  # must have a non-empty name
        ):
            return obj
    return None


def load_plugin_file(path: Path) -> type[ModuleBase]:
    """
    Import a single plugin file and return the ModuleBase subclass it defines.
    Raises PluginLoadError on any problem.
    """
    spec = importlib.util.spec_from_file_location(f"ha_copilot_plugin_{path.stem}", path)
    if spec is None or spec.loader is None:
        raise PluginLoadError(f"Cannot create module spec for {path}")

    mod = importlib.util.module_from_spec(spec)
    # Register in sys.modules so relative imports inside the plugin work
    sys.modules[spec.name] = mod
    try:
        spec.loader.exec_module(mod)  # type: ignore[union-attr]
    except Exception as exc:
        del sys.modules[spec.name]
        raise PluginLoadError(f"Error executing plugin {path.name}: {exc}") from exc

    cls = _find_module_class(mod)
    if cls is None:
        del sys.modules[spec.name]
        raise PluginLoadError(
            f"Plugin {path.name} must define a ModuleBase subclass with a non-empty `name`"
        )
    return cls


def load_all_plugins(registry: "ModuleRegistry") -> list[str]:
    """
    Scan PLUGINS_DIR for .py files, load each, register with registry.
    Returns list of successfully loaded plugin names.
    Failures are logged but do not raise.
    """
    if not PLUGINS_DIR.exists():
        logger.debug("plugin_dir_not_found", path=str(PLUGINS_DIR))
        return []

    loaded: list[str] = []
    for path in sorted(PLUGINS_DIR.glob("*.py")):
        try:
            cls = load_plugin_file(path)
            instance = cls()
            registry.register(instance)
            loaded.append(instance.name)
            logger.info("plugin_loaded", name=instance.name, file=path.name)
        except Exception as exc:
            logger.error("plugin_load_failed", file=path.name, error=str(exc))

    return loaded
