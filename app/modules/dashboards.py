"""
Dashboard/Lovelace management — Phase 6.

/dash              — list dashboards and their views
/dash <name> show  — show view cards for a specific dashboard/view
/dash suggest      — AI generates a Lovelace view suggestion
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

from telegram.constants import ParseMode

from app.bot.formatters import bold, code, error_msg, escape_md
from app.core.module_base import ModuleBase
from app.observability.logger import get_logger

if TYPE_CHECKING:
    from app.bot.handler import CommandContext
    from app.core.module_registry import AppContext

logger = get_logger(__name__)

# Telegram message length limit headroom
_MAX_YAML_CHARS = 3600


class DashboardsModule(ModuleBase):
    name = "dashboards"
    description = "Dashboard/Lovelace management"
    commands: list[str] = ["dash"]

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
        if not args:
            await self._cmd_list(context)
            return

        sub = args[0].lower()
        if sub == "suggest":
            await self._cmd_suggest(context)
        else:
            # /dash <name> show  — args[0]=name, args[1]="show"
            action = args[1].lower() if len(args) > 1 else "show"
            if action == "show":
                await self._cmd_show_view(args[0], context)
            else:
                await self._reply(
                    context,
                    "Usage: `/dash`, `/dash <view> show`, `/dash suggest`",
                )

    # ------------------------------------------------------------------ #

    async def _get_lovelace(self, url_path: str | None = None) -> dict[str, Any]:
        """Fetch Lovelace config via WebSocket."""
        ws = self._app.extra.get("websocket")
        if not ws:
            raise RuntimeError("WebSocket not available")
        cmd: dict = {"type": "lovelace/config"}
        if url_path:
            cmd["url_path"] = url_path
        result = await ws.send_command(cmd)
        if not isinstance(result, dict):
            raise RuntimeError("Unexpected Lovelace response format")
        return result

    async def _cmd_list(self, context: "CommandContext") -> None:
        try:
            config = await self._get_lovelace()
        except Exception as exc:
            await self._reply(context, error_msg(f"Cannot fetch dashboards: {exc}"))
            return

        title = config.get("title", "Home")
        views: list[dict] = config.get("views", [])

        lines = [bold(f"Dashboard: {escape_md(title)}"), ""]
        if not views:
            lines.append("_No views configured_")
        else:
            for i, v in enumerate(views, 1):
                view_title = v.get("title", f"View {i}")
                path = v.get("path", "")
                card_count = len(v.get("cards", []))
                path_str = f" — {code(path)}" if path else ""
                lines.append(
                    f"{i}\\. {escape_md(view_title)}{path_str} "
                    f"\\({card_count} cards\\)"
                )

        lines.append("")
        lines.append("_Use_ `/dash <view> show` _to see cards_")
        await context.update.message.reply_text(
            "\n".join(lines), parse_mode=ParseMode.MARKDOWN_V2
        )

    async def _cmd_show_view(self, name: str, context: "CommandContext") -> None:
        try:
            config = await self._get_lovelace()
        except Exception as exc:
            await self._reply(context, error_msg(f"Cannot fetch dashboards: {exc}"))
            return

        views: list[dict] = config.get("views", [])
        # Match by title (case-insensitive) or path
        target = None
        for v in views:
            if (
                v.get("title", "").lower() == name.lower()
                or v.get("path", "").lower() == name.lower()
            ):
                target = v
                break

        if target is None:
            names = [v.get("title", v.get("path", "?")) for v in views]
            await self._reply(
                context,
                error_msg(
                    f"View '{name}' not found. Available: {', '.join(names)}"
                ),
            )
            return

        import io
        from ruamel.yaml import YAML

        _yaml = YAML()
        _yaml.default_flow_style = False
        buf = io.StringIO()
        _yaml.dump(dict(target), buf)
        yaml_str = buf.getvalue()

        truncated = ""
        if len(yaml_str) > _MAX_YAML_CHARS:
            yaml_str = yaml_str[:_MAX_YAML_CHARS]
            truncated = "\n_\\.\\.\\. truncated_"

        safe = yaml_str.replace("\\", "\\\\").replace("`", "\\`")
        msg = (
            f"{bold(escape_md(target.get('title', name)))}\n\n"
            f"```yaml\n{safe}\n```{truncated}"
        )
        await context.update.message.reply_text(
            msg, parse_mode=ParseMode.MARKDOWN_V2
        )

    async def _cmd_suggest(self, context: "CommandContext") -> None:
        generator = self._app.extra.get("yaml_generator")
        if not generator:
            # Lazy-build the generator if we have the pieces
            try:
                from app.ai.yaml_generator import YAMLGenerator

                generator = YAMLGenerator(
                    config=self._app.config,
                    discovery=self._app.extra["discovery"],
                )
                self._app.extra["yaml_generator"] = generator
            except Exception as exc:
                await self._reply(context, error_msg(f"AI generator unavailable: {exc}"))
                return

        await self._reply(context, "⏳ Generating dashboard suggestion\\.\\.\\.")
        try:
            view_yaml = await generator.generate_dashboard(
                "Suggest a useful main Lovelace view based on the available entities."
            )
        except Exception as exc:
            await self._reply(context, error_msg(f"AI generation failed: {exc}"))
            return

        truncated = ""
        if len(view_yaml) > _MAX_YAML_CHARS:
            view_yaml = view_yaml[:_MAX_YAML_CHARS]
            truncated = "\n_\\.\\.\\. truncated_"

        safe = view_yaml.replace("\\", "\\\\").replace("`", "\\`")
        msg = (
            f"{bold('AI Dashboard Suggestion')}\n\n"
            f"```yaml\n{safe}\n```{truncated}\n\n"
            "_Review and add to your Lovelace config manually\\._"
        )
        await context.update.message.reply_text(
            msg, parse_mode=ParseMode.MARKDOWN_V2
        )

    async def _reply(self, context: "CommandContext", text: str) -> None:
        await context.update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN_V2)
