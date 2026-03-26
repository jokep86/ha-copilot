"""
Media commands — Phase 7.

/camera <entity_id>        — send camera snapshot photo
/chart <entity_id> [hours] — send entity history chart as PNG
/export automations|scenes|config — send as downloadable file
/audit export [days]       — export AI audit log as JSON file
"""
from __future__ import annotations

import io
from typing import TYPE_CHECKING

from telegram.constants import ParseMode

from app.bot.formatters import bold, code, error_msg, escape_md, warning_msg
from app.core.module_base import ModuleBase
from app.observability.logger import get_logger

if TYPE_CHECKING:
    from app.bot.handler import CommandContext
    from app.core.module_registry import AppContext

logger = get_logger(__name__)

_DEFAULT_CHART_HOURS = 24
_MAX_CHART_HOURS = 168  # 7 days


class MediaModule(ModuleBase):
    name = "media"
    description = "Camera snapshots, history charts, file exports"
    commands: list[str] = ["camera", "chart", "export", "audit"]

    async def setup(self, app: "AppContext") -> None:
        self._app = app
        self._ha = app.ha_client
        self._discovery = app.extra.get("discovery")

    async def teardown(self) -> None:
        pass

    async def handle_command(
        self,
        cmd: str,
        args: list[str],
        context: "CommandContext",
    ) -> None:
        if cmd == "camera":
            await self._cmd_camera(args, context)
        elif cmd == "chart":
            await self._cmd_chart(args, context)
        elif cmd == "export":
            await self._cmd_export(args, context)
        elif cmd == "audit":
            await self._cmd_audit(args, context)

    # ------------------------------------------------------------------ #

    async def _cmd_camera(self, args: list[str], context: "CommandContext") -> None:
        if not args:
            await self._reply(context, "Usage: `/camera <entity_id>`")
            return

        raw = args[0]
        # Allow short form: "front_door" → "camera.front_door"
        if "." not in raw:
            raw = f"camera.{raw}"
        if self._discovery:
            entity_id, err = await self._discovery.resolve_entity_id(raw)
            if err:
                await self._reply(context, error_msg(err))
                return
        else:
            entity_id = raw

        try:
            from app.media.camera import fetch_snapshot, CameraError
            image_bytes = await fetch_snapshot(self._ha, entity_id)
        except Exception as exc:
            await self._reply(context, error_msg(f"Camera error: {exc}"))
            return

        await context.update.message.reply_photo(
            photo=io.BytesIO(image_bytes),
            caption=escape_md(entity_id),
            parse_mode=ParseMode.MARKDOWN_V2,
        )

    async def _cmd_chart(self, args: list[str], context: "CommandContext") -> None:
        if not args:
            await self._reply(context, "Usage: `/chart <entity_id> [hours]`")
            return

        if self._discovery:
            entity_id, err = await self._discovery.resolve_entity_id(args[0])
            if err:
                await self._reply(context, error_msg(err))
                return
        else:
            entity_id = args[0]
        hours = _DEFAULT_CHART_HOURS
        if len(args) > 1:
            try:
                hours = min(int(args[1]), _MAX_CHART_HOURS)
            except ValueError:
                await self._reply(context, error_msg(f"Invalid hours value: {args[1]}"))
                return

        await self._reply(context, f"⏳ Fetching history for {code(escape_md(entity_id))}\\.\\.\\.")

        try:
            state = await self._ha.get_state(entity_id)
        except Exception as exc:
            await self._reply(context, error_msg(f"Entity not found: {exc}"))
            return

        fname = state.get("attributes", {}).get("friendly_name", entity_id)
        unit = state.get("attributes", {}).get("unit_of_measurement", "")

        try:
            history = await self._ha.get_history(entity_id, hours=hours)
        except Exception as exc:
            await self._reply(context, error_msg(f"History fetch failed: {exc}"))
            return

        from app.media.charts import generate_history_chart, ChartError
        try:
            chart_bytes = generate_history_chart(entity_id, fname, history, unit, hours)
        except ChartError as exc:
            await self._reply(context, error_msg(str(exc)))
            return

        if chart_bytes is None:
            # plotly not available — send text summary instead
            await self._reply(
                context,
                warning_msg(
                    f"Chart unavailable (plotly/kaleido not installed). "
                    f"Use /history {entity_id} for text history."
                ),
            )
            return

        await context.update.message.reply_photo(
            photo=io.BytesIO(chart_bytes),
            caption=f"{escape_md(fname)} — last {hours}h",
            parse_mode=ParseMode.MARKDOWN_V2,
        )

    async def _cmd_export(self, args: list[str], context: "CommandContext") -> None:
        export_type = args[0].lower() if args else ""
        if export_type not in ("automations", "scenes", "config"):
            await self._reply(
                context,
                "Usage: `/export automations`, `/export scenes`, or `/export config`",
            )
            return

        from app.media.export import export_automations, export_scenes, export_config, ExportError
        try:
            if export_type == "automations":
                data, filename = await export_automations(self._ha)
            elif export_type == "scenes":
                data, filename = await export_scenes(self._ha)
            else:
                data, filename = export_config()
        except ExportError as exc:
            await self._reply(context, error_msg(str(exc)))
            return

        await context.update.message.reply_document(
            document=io.BytesIO(data),
            filename=filename,
            caption=escape_md(f"Exported: {filename}"),
            parse_mode=ParseMode.MARKDOWN_V2,
        )

    async def _cmd_audit(self, args: list[str], context: "CommandContext") -> None:
        sub = args[0].lower() if args else ""
        if sub != "export":
            await self._reply(context, "Usage: `/audit export [days]`")
            return

        days = 30
        if len(args) > 1:
            try:
                days = int(args[1])
            except ValueError:
                await self._reply(context, error_msg(f"Invalid days value: {args[1]}"))
                return

        from app.media.export import export_audit_log, ExportError
        try:
            data, filename = await export_audit_log(self._app.db, days)
        except ExportError as exc:
            await self._reply(context, error_msg(str(exc)))
            return

        await context.update.message.reply_document(
            document=io.BytesIO(data),
            filename=filename,
            caption=escape_md(f"AI audit log — last {days} days"),
            parse_mode=ParseMode.MARKDOWN_V2,
        )

    async def _reply(self, context: "CommandContext", text: str) -> None:
        await context.update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN_V2)
