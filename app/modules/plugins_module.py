"""
Plugin management — Fase 2.

/plugins        — list loaded plugins (both built-in and community)
/plugins load   — re-scan /data/plugins/ and load any new .py files
/reload <name>  — hot-reload a community plugin without restarting the add-on
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from telegram.constants import ParseMode

from app.bot.formatters import bold, code, error_msg, escape_md, success_msg
from app.core.module_base import ModuleBase
from app.observability.logger import get_logger

if TYPE_CHECKING:
    from app.bot.handler import CommandContext
    from app.core.module_registry import AppContext

logger = get_logger(__name__)


class PluginsModule(ModuleBase):
    name = "plugins"
    description = "Plugin management: list, load, hot-reload community plugins"
    commands: list[str] = ["plugins", "reload"]

    async def setup(self, app: "AppContext") -> None:
        self._app = app

    async def teardown(self) -> None:
        pass

    async def handle_command(
        self, cmd: str, args: list[str], context: "CommandContext"
    ) -> None:
        if cmd == "reload":
            module_name = args[0] if args else ""
            await self._cmd_reload(module_name, context)
        elif args and args[0] == "load":
            await self._cmd_load_new(context)
        else:
            await self._cmd_list(context)

    # ------------------------------------------------------------------ #

    async def _cmd_list(self, context: "CommandContext") -> None:
        registry = self._app.extra.get("registry")
        if not registry:
            await self._reply(context, error_msg("Registry not available."))
            return

        from app.core.plugin_loader import PLUGINS_DIR

        modules = registry.modules
        # Built-ins live in app/modules/ or app/ai/ — plugins live in /data/plugins/
        plugin_names: set[str] = set()
        if PLUGINS_DIR.exists():
            plugin_names = {p.stem for p in PLUGINS_DIR.glob("*.py")}

        lines = [bold("Loaded modules"), ""]
        for name, mod in sorted(modules.items()):
            tag = " 🔌" if name in plugin_names else ""
            cmds = ", ".join(code(f"/{c}") for c in mod.commands) if mod.commands else "—"
            lines.append(f"• {bold(escape_md(name))}{tag}\n  {escape_md(mod.description)}\n  {cmds}")

        lines.append("")
        lines.append(f"_{len(modules)} modules total_")
        if PLUGINS_DIR.exists():
            lines.append(f"_Plugin dir: `{escape_md(str(PLUGINS_DIR))}`_")
        else:
            lines.append(f"_No plugin dir \\({escape_md(str(PLUGINS_DIR))} not found\\)_")

        await context.update.message.reply_text(
            "\n".join(lines), parse_mode=ParseMode.MARKDOWN_V2
        )

    async def _cmd_load_new(self, context: "CommandContext") -> None:
        """Re-scan /data/plugins/ and register any new plugins."""
        registry = self._app.extra.get("registry")
        if not registry:
            await self._reply(context, error_msg("Registry not available."))
            return

        from app.core.plugin_loader import PLUGINS_DIR, load_all_plugins

        if not PLUGINS_DIR.exists():
            await self._reply(
                context,
                escape_md(f"Plugin directory {PLUGINS_DIR} does not exist."),
            )
            return

        # Only load files whose module name is not yet registered
        existing = set(registry.modules.keys())
        newly_loaded: list[str] = []
        errors: list[str] = []

        from app.core.plugin_loader import load_plugin_file

        for path in sorted(PLUGINS_DIR.glob("*.py")):
            # Use stem (filename without .py) as initial name check
            try:
                cls = load_plugin_file(path)
                instance = cls()
                if instance.name in existing:
                    continue  # already loaded
                registry.register(instance)
                await instance.setup(self._app)
                newly_loaded.append(instance.name)
                logger.info("plugin_hot_loaded", name=instance.name, file=path.name)
            except Exception as exc:
                errors.append(f"{path.name}: {exc}")
                logger.error("plugin_hot_load_failed", file=path.name, error=str(exc))

        parts: list[str] = []
        if newly_loaded:
            names = ", ".join(code(n) for n in newly_loaded)
            parts.append(success_msg(f"Loaded: {names}"))
        else:
            parts.append("No new plugins found\\.")
        for err in errors:
            parts.append(error_msg(escape_md(err)))

        await self._reply(context, "\n".join(parts))

    async def _cmd_reload(self, module_name: str, context: "CommandContext") -> None:
        """Hot-reload any module — plugin (re-imports file) or built-in (fresh instance)."""
        if not module_name:
            await self._reply(context, "Usage: /reload \\<module\\_name\\>")
            return

        registry = self._app.extra.get("registry")
        if not registry:
            await self._reply(context, error_msg("Registry not available."))
            return

        if module_name not in registry.modules:
            await self._reply(
                context,
                escape_md(f"Module '{module_name}' not registered. Use /plugins to list modules."),
            )
            return

        try:
            # Try community plugin reload first (re-imports from /data/plugins/)
            await registry.reload_plugin(module_name, self._app)
            await self._reply(context, success_msg(f"Plugin '{module_name}' reloaded from file."))
            logger.info("plugin_reloaded_via_command", name=module_name)
        except FileNotFoundError:
            # Built-in module — teardown + fresh instantiation of same class
            try:
                await registry.reload_builtin(module_name, self._app)
                await self._reply(
                    context,
                    success_msg(f"Module '{module_name}' reloaded (state reset, config reapplied)."),
                )
                logger.info("builtin_reloaded_via_command", name=module_name)
            except Exception as exc:
                await self._reply(context, error_msg(f"Reload failed: {exc}"))
        except Exception as exc:
            await self._reply(context, error_msg(f"Reload failed: {exc}"))

    async def _reply(self, context: "CommandContext", text: str) -> None:
        await context.update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN_V2)
