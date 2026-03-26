"""
Unit tests for MediaModule.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from app.modules.media import MediaModule


def _app(camera_bytes=b"FAKEJPEG", state=None, history=None, db=None):
    app = MagicMock()
    app.ha_client.get_camera_image = AsyncMock(return_value=camera_bytes)
    app.ha_client.get_state = AsyncMock(
        return_value=state
        or {
            "entity_id": "sensor.temp",
            "state": "22",
            "attributes": {"friendly_name": "Temperature", "unit_of_measurement": "°C"},
        }
    )
    app.ha_client.get_history = AsyncMock(
        return_value=history
        or [
            [
                {"state": "20.0", "last_changed": "2026-03-24T00:00:00Z"},
                {"state": "22.0", "last_changed": "2026-03-24T12:00:00Z"},
            ]
        ]
    )
    app.ha_client.get_automations = AsyncMock(
        return_value=[{"alias": "My Auto", "trigger": [], "action": []}]
    )
    app.ha_client.get_scenes = AsyncMock(
        return_value=[{"name": "Evening", "entities": {}}]
    )
    app.db = db or MagicMock()
    discovery = MagicMock()
    discovery.resolve_entity_id = AsyncMock(return_value=("sensor.temp", None))
    app.extra = {"discovery": discovery}
    return app


def _context():
    ctx = MagicMock()
    ctx.update.message.reply_text = AsyncMock()
    ctx.update.message.reply_photo = AsyncMock()
    ctx.update.message.reply_document = AsyncMock()
    return ctx


class TestMediaModule:
    def test_commands(self):
        assert set(["camera", "chart", "export", "audit"]).issubset(set(MediaModule.commands))

    async def test_camera_no_args(self):
        m = MediaModule()
        await m.setup(_app())
        ctx = _context()
        await m.handle_command("camera", [], ctx)
        text = ctx.update.message.reply_text.call_args[0][0]
        assert "usage" in text.lower()

    async def test_camera_sends_photo(self):
        m = MediaModule()
        await m.setup(_app(camera_bytes=b"\xff\xd8\xff" + b"x" * 100))
        ctx = _context()
        await m.handle_command("camera", ["camera.front_door"], ctx)
        ctx.update.message.reply_photo.assert_called_once()

    async def test_camera_short_form(self):
        """'front_door' should be expanded to 'camera.front_door'."""
        m = MediaModule()
        app = _app()
        app.extra["discovery"].resolve_entity_id = AsyncMock(return_value=("camera.front_door", None))
        await m.setup(app)
        ctx = _context()
        await m.handle_command("camera", ["front_door"], ctx)
        app.ha_client.get_camera_image.assert_called_once_with("camera.front_door")

    async def test_camera_error(self):
        m = MediaModule()
        app = _app()
        app.ha_client.get_camera_image = AsyncMock(side_effect=Exception("no stream"))
        await m.setup(app)
        ctx = _context()
        await m.handle_command("camera", ["camera.broken"], ctx)
        text = ctx.update.message.reply_text.call_args[0][0]
        assert "error" in text.lower() or "no stream" in text.lower()

    async def test_chart_no_args(self):
        m = MediaModule()
        await m.setup(_app())
        ctx = _context()
        await m.handle_command("chart", [], ctx)
        text = ctx.update.message.reply_text.call_args[0][0]
        assert "usage" in text.lower()

    async def test_chart_plotly_unavailable_sends_warning(self):
        m = MediaModule()
        await m.setup(_app())
        ctx = _context()
        # Patch at the source module level
        with patch("app.media.charts.generate_history_chart", return_value=None):
            await m.handle_command("chart", ["sensor.temp", "12"], ctx)
        # Last reply should be the warning
        final = ctx.update.message.reply_text.call_args_list[-1][0][0]
        assert "unavailable" in final.lower() or "not installed" in final.lower()

    async def test_chart_sends_photo_when_chart_available(self):
        m = MediaModule()
        await m.setup(_app())
        ctx = _context()
        with patch("app.media.charts.generate_history_chart", return_value=b"PNG"):
            await m.handle_command("chart", ["sensor.temp"], ctx)
        ctx.update.message.reply_photo.assert_called_once()

    async def test_export_automations(self):
        m = MediaModule()
        await m.setup(_app())
        ctx = _context()
        await m.handle_command("export", ["automations"], ctx)
        ctx.update.message.reply_document.assert_called_once()
        _, kwargs = ctx.update.message.reply_document.call_args
        assert kwargs.get("filename") == "automations.yaml" or "automations" in str(
            ctx.update.message.reply_document.call_args
        )

    async def test_export_invalid_type(self):
        m = MediaModule()
        await m.setup(_app())
        ctx = _context()
        await m.handle_command("export", ["logs"], ctx)
        text = ctx.update.message.reply_text.call_args[0][0]
        assert "usage" in text.lower()

    async def test_audit_export(self):
        db = MagicMock()
        cursor = MagicMock()
        cursor.fetchall = AsyncMock(return_value=[])
        db.conn.execute = AsyncMock(return_value=cursor)
        m = MediaModule()
        await m.setup(_app(db=db))
        ctx = _context()
        await m.handle_command("audit", ["export", "7"], ctx)
        ctx.update.message.reply_document.assert_called_once()

    async def test_audit_wrong_subcommand(self):
        m = MediaModule()
        await m.setup(_app())
        ctx = _context()
        await m.handle_command("audit", ["stats"], ctx)
        text = ctx.update.message.reply_text.call_args[0][0]
        assert "usage" in text.lower()
