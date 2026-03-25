"""
Unit tests for ConfigManagerModule.
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from app.modules.config_manager import ConfigManagerModule


def _app(config_entries=None, users=None):
    app = MagicMock()
    app.ha_client.get_config_entries = AsyncMock(return_value=config_entries or [])
    app.ha_client.check_config = AsyncMock(return_value={"result": "valid", "errors": ""})
    ws = MagicMock()
    ws.send_command = AsyncMock(return_value=users or [])
    app.extra = {"websocket": ws}
    return app


def _context():
    ctx = MagicMock()
    ctx.update.message.reply_text = AsyncMock()
    return ctx


class TestConfigManagerModule:
    def test_setup(self):
        m = ConfigManagerModule()
        app = _app()
        # setup stores app and ha_client
        import asyncio
        asyncio.get_event_loop().run_until_complete(m.setup(app))
        assert m._ha is app.ha_client

    def test_commands(self):
        m = ConfigManagerModule()
        assert "config" in m.commands
        assert "integrations" in m.commands
        assert "users" in m.commands

    async def test_config_show_file_not_found(self):
        m = ConfigManagerModule()
        await m.setup(_app())
        ctx = _context()
        with patch("app.modules.config_manager._CONFIG_FILE", Path("/nonexistent/config.yaml")):
            await m.handle_command("config", [], ctx)
        text = ctx.update.message.reply_text.call_args[0][0]
        assert "not found" in text.lower() or "cannot" in text.lower()

    async def test_config_check_valid(self):
        m = ConfigManagerModule()
        app = _app()
        await m.setup(app)
        ctx = _context()
        await m.handle_command("config", ["check"], ctx)
        app.ha_client.check_config.assert_called_once()
        text = ctx.update.message.reply_text.call_args[0][0]
        assert "valid" in text.lower()

    async def test_config_check_invalid(self):
        m = ConfigManagerModule()
        app = _app()
        app.ha_client.check_config = AsyncMock(
            return_value={"result": "invalid", "errors": "bad yaml"}
        )
        await m.setup(app)
        ctx = _context()
        await m.handle_command("config", ["check"], ctx)
        text = ctx.update.message.reply_text.call_args[0][0]
        assert "failed" in text.lower() or "bad yaml" in text

    async def test_integrations_list(self):
        entries = [
            {"domain": "zwave_js", "title": "Z-Wave JS"},
            {"domain": "zwave_js", "title": "Z-Wave JS 2"},
            {"domain": "mqtt", "title": "MQTT"},
        ]
        m = ConfigManagerModule()
        await m.setup(_app(config_entries=entries))
        ctx = _context()
        await m.handle_command("integrations", [], ctx)
        text = ctx.update.message.reply_text.call_args[0][0]
        # domain names are MarkdownV2-escaped: zwave_js → zwave\_js
        assert "zwave" in text
        assert "mqtt" in text

    async def test_integrations_empty(self):
        m = ConfigManagerModule()
        await m.setup(_app(config_entries=[]))
        ctx = _context()
        await m.handle_command("integrations", [], ctx)
        text = ctx.update.message.reply_text.call_args[0][0]
        assert "no integrations" in text.lower()

    async def test_users_list(self):
        users = [
            {"name": "Admin", "is_active": True, "group_ids": ["system-admin"], "system_generated": False},
            {"name": "Guest", "is_active": True, "group_ids": [], "system_generated": False},
        ]
        m = ConfigManagerModule()
        await m.setup(_app(users=users))
        ctx = _context()
        await m.handle_command("users", [], ctx)
        text = ctx.update.message.reply_text.call_args[0][0]
        assert "Admin" in text
        assert "Guest" in text

    async def test_users_no_websocket(self):
        m = ConfigManagerModule()
        app = _app()
        app.extra = {}  # no websocket
        await m.setup(app)
        ctx = _context()
        await m.handle_command("users", [], ctx)
        text = ctx.update.message.reply_text.call_args[0][0]
        assert "not available" in text.lower()

    async def test_integrations_api_error(self):
        m = ConfigManagerModule()
        app = _app()
        app.ha_client.get_config_entries = AsyncMock(side_effect=Exception("timeout"))
        await m.setup(app)
        ctx = _context()
        await m.handle_command("integrations", [], ctx)
        text = ctx.update.message.reply_text.call_args[0][0]
        assert "timeout" in text or "could not" in text.lower()
