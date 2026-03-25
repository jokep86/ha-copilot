"""
Unit tests for DashboardsModule.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
import pytest

from app.modules.dashboards import DashboardsModule

_LOVELACE = {
    "title": "My Home",
    "views": [
        {
            "title": "Living Room",
            "path": "living",
            "cards": [{"type": "entities"}, {"type": "glance"}],
        },
        {
            "title": "Security",
            "path": "security",
            "cards": [{"type": "glance"}],
        },
    ],
}


def _app(lovelace=None, ws_error=None):
    ws = MagicMock()
    if ws_error:
        ws.send_command = AsyncMock(side_effect=ws_error)
    else:
        ws.send_command = AsyncMock(return_value=lovelace or _LOVELACE)
    app = MagicMock()
    app.extra = {"websocket": ws}
    return app


def _context():
    ctx = MagicMock()
    ctx.update.message.reply_text = AsyncMock()
    return ctx


class TestDashboardsModule:
    def test_commands(self):
        assert "dash" in DashboardsModule.commands

    async def test_list_shows_views(self):
        m = DashboardsModule()
        await m.setup(_app())
        ctx = _context()
        await m.handle_command("dash", [], ctx)
        text = ctx.update.message.reply_text.call_args[0][0]
        assert "Living Room" in text
        assert "Security" in text

    async def test_list_shows_card_count(self):
        m = DashboardsModule()
        await m.setup(_app())
        ctx = _context()
        await m.handle_command("dash", [], ctx)
        text = ctx.update.message.reply_text.call_args[0][0]
        # Living Room has 2 cards
        assert "2 cards" in text

    async def test_show_view_by_title(self):
        m = DashboardsModule()
        await m.setup(_app())
        ctx = _context()
        await m.handle_command("dash", ["Living Room", "show"], ctx)
        text = ctx.update.message.reply_text.call_args[0][0]
        # Should show YAML containing 'living' or 'entities'
        assert "living" in text.lower() or "entities" in text.lower()

    async def test_show_view_by_path(self):
        m = DashboardsModule()
        await m.setup(_app())
        ctx = _context()
        await m.handle_command("dash", ["security", "show"], ctx)
        text = ctx.update.message.reply_text.call_args[0][0]
        assert "Security" in text or "glance" in text

    async def test_show_view_not_found(self):
        m = DashboardsModule()
        await m.setup(_app())
        ctx = _context()
        await m.handle_command("dash", ["kitchen", "show"], ctx)
        text = ctx.update.message.reply_text.call_args[0][0]
        assert "not found" in text.lower()

    async def test_list_ws_error(self):
        m = DashboardsModule()
        await m.setup(_app(ws_error=RuntimeError("WS disconnected")))
        ctx = _context()
        await m.handle_command("dash", [], ctx)
        text = ctx.update.message.reply_text.call_args[0][0]
        assert "cannot fetch" in text.lower() or "ws disconnected" in text.lower()

    async def test_list_no_websocket(self):
        m = DashboardsModule()
        app = MagicMock()
        app.extra = {}
        await m.setup(app)
        ctx = _context()
        await m.handle_command("dash", [], ctx)
        text = ctx.update.message.reply_text.call_args[0][0]
        assert "not available" in text.lower() or "cannot fetch" in text.lower()

    async def test_suggest_calls_generator(self):
        m = DashboardsModule()
        generator = MagicMock()
        generator.generate_dashboard = AsyncMock(
            return_value="title: Main\npath: main\ncards: []"
        )
        app = _app()
        app.extra["yaml_generator"] = generator
        await m.setup(app)
        ctx = _context()
        await m.handle_command("dash", ["suggest"], ctx)
        generator.generate_dashboard.assert_called_once()
        # Should have been called twice: once "thinking", once with the YAML
        assert ctx.update.message.reply_text.call_count == 2
        final_text = ctx.update.message.reply_text.call_args_list[-1][0][0]
        assert "yaml" in final_text.lower() or "main" in final_text

    async def test_suggest_generator_error(self):
        m = DashboardsModule()
        generator = MagicMock()
        generator.generate_dashboard = AsyncMock(side_effect=Exception("Claude down"))
        app = _app()
        app.extra["yaml_generator"] = generator
        await m.setup(app)
        ctx = _context()
        await m.handle_command("dash", ["suggest"], ctx)
        final_text = ctx.update.message.reply_text.call_args_list[-1][0][0]
        assert "failed" in final_text.lower() or "claude down" in final_text.lower()
