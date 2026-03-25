"""
Unit tests for MigrationModule.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from app.modules.migration import MigrationModule


def _app(ai_enabled=True, ha_version="2026.3.4", entries=None):
    app = MagicMock()
    app.config.ai_enabled = ai_enabled
    app.config.ai_model = "claude-sonnet-4-20250514"
    app.config.ai_max_tokens = 512
    app.config.anthropic_api_key = "test-key"
    app.ha_client.get_config = AsyncMock(return_value={"version": ha_version})
    app.ha_client.get_config_entries = AsyncMock(
        return_value=entries or [
            {"domain": "zwave_js", "title": "Z-Wave JS"},
            {"domain": "mqtt", "title": "MQTT"},
        ]
    )
    return app


def _context():
    ctx = MagicMock()
    ctx.update.message.reply_text = AsyncMock()
    return ctx


def _mock_claude(text="1. [INFO] All looks good."):
    response = MagicMock()
    response.content = [MagicMock(text=text)]
    response.usage.input_tokens = 100
    response.usage.output_tokens = 50
    client = MagicMock()
    client.messages.create = AsyncMock(return_value=response)
    return client


class TestMigrationModule:
    def test_commands(self):
        assert "migrate" in MigrationModule.commands

    async def test_ai_disabled(self):
        m = MigrationModule()
        await m.setup(_app(ai_enabled=False))
        ctx = _context()
        await m.handle_command("migrate", [], ctx)
        text = ctx.update.message.reply_text.call_args[0][0]
        assert "disabled" in text.lower()

    async def test_check_calls_claude(self):
        m = MigrationModule()
        await m.setup(_app())
        ctx = _context()
        ai_client = _mock_claude("1. [WARNING] Old zwave domain detected.")
        with patch("app.modules.migration.anthropic.AsyncAnthropic", return_value=ai_client):
            await m.handle_command("migrate", ["check"], ctx)
        # 2 calls: "analyzing..." + result
        assert ctx.update.message.reply_text.call_count == 2
        final = ctx.update.message.reply_text.call_args_list[-1][0][0]
        assert "2026" in final or "Migration" in final

    async def test_check_claude_error(self):
        m = MigrationModule()
        await m.setup(_app())
        ctx = _context()
        ai_client = MagicMock()
        ai_client.messages.create = AsyncMock(side_effect=Exception("API down"))
        with patch("app.modules.migration.anthropic.AsyncAnthropic", return_value=ai_client):
            await m.handle_command("migrate", [], ctx)
        final = ctx.update.message.reply_text.call_args_list[-1][0][0]
        assert "failed" in final.lower() or "api down" in final.lower()

    async def test_ha_config_failure_is_tolerated(self):
        """Migration check should still run even if HA config is unavailable."""
        m = MigrationModule()
        app = _app()
        app.ha_client.get_config = AsyncMock(side_effect=Exception("HA offline"))
        await m.setup(app)
        ctx = _context()
        ai_client = _mock_claude("1. [INFO] Looks ok.")
        with patch("app.modules.migration.anthropic.AsyncAnthropic", return_value=ai_client):
            await m.handle_command("migrate", [], ctx)
        # Should complete without raising
        assert ctx.update.message.reply_text.call_count == 2

    async def test_unknown_subcommand(self):
        m = MigrationModule()
        await m.setup(_app())
        ctx = _context()
        await m.handle_command("migrate", ["badcmd"], ctx)
        text = ctx.update.message.reply_text.call_args[0][0]
        assert "usage" in text.lower()
