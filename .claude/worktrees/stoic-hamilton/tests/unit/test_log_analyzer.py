"""
Unit tests for LogAnalyzerModule.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from app.modules.log_analyzer import LogAnalyzerModule


def _make_app(logs: str = ""):
    sup = MagicMock()
    sup.get_logs = AsyncMock(return_value=logs)

    config = MagicMock()
    config.anthropic_api_key = "test-key"
    config.ai_enabled = True
    config.ai_model = "claude-haiku-4-5-20251001"
    config.ai_max_tokens = 512

    app = MagicMock()
    app.supervisor_client = sup
    app.config = config
    return app, sup


def _ctx():
    ctx = MagicMock()
    ctx.user_id = 1
    ctx.update = MagicMock()
    ctx.update.message = MagicMock()
    ctx.update.message.reply_text = AsyncMock()
    return ctx


class TestLogAnalyzerModule:
    async def test_logs_default_source(self):
        mod = LogAnalyzerModule()
        app, sup = _make_app("2026-03-01 INFO Starting\n2026-03-01 ERROR Failed\n")

        with patch("anthropic.AsyncAnthropic"):
            await mod.setup(app)

        await mod.handle_command("logs", [], _ctx())
        sup.get_logs.assert_awaited_once_with("core")

    async def test_logs_custom_source(self):
        mod = LogAnalyzerModule()
        app, sup = _make_app("some log line\n")

        with patch("anthropic.AsyncAnthropic"):
            await mod.setup(app)

        await mod.handle_command("logs", ["supervisor"], _ctx())
        sup.get_logs.assert_awaited_once_with("supervisor")

    async def test_logs_level_filter(self):
        mod = LogAnalyzerModule()
        logs = "INFO Starting\nERROR Something broke\nDEBUG Details\n"
        app, sup = _make_app(logs)

        with patch("anthropic.AsyncAnthropic"):
            await mod.setup(app)

        ctx = _ctx()
        await mod.handle_command("logs", ["core", "ERROR"], ctx)
        text = ctx.update.message.reply_text.call_args[0][0]
        assert "ERROR" in text or "broke" in text

    async def test_logs_empty_returns_message(self):
        mod = LogAnalyzerModule()
        app, sup = _make_app("")

        with patch("anthropic.AsyncAnthropic"):
            await mod.setup(app)

        ctx = _ctx()
        await mod.handle_command("logs", ["core"], ctx)
        ctx.update.message.reply_text.assert_awaited_once()

    async def test_analyze_calls_claude(self):
        mod = LogAnalyzerModule()
        logs = "ERROR Integration failed\nERROR Connection refused\n"
        app, sup = _make_app(logs)

        ai_mock = MagicMock()
        ai_response = MagicMock()
        ai_response.content = [MagicMock(text="Root cause: network error. Fix: check connectivity.")]
        ai_response.usage = MagicMock(input_tokens=100, output_tokens=50)
        ai_mock.messages = MagicMock()
        ai_mock.messages.create = AsyncMock(return_value=ai_response)

        with patch("anthropic.AsyncAnthropic", return_value=ai_mock):
            await mod.setup(app)

        ctx = _ctx()
        await mod.handle_command("logs", ["analyze", "core"], ctx)

        ai_mock.messages.create.assert_awaited_once()
        # Should have sent at least 2 messages: "Analyzing..." + analysis
        assert ctx.update.message.reply_text.await_count >= 2

    async def test_analyze_no_errors_skips_claude(self):
        mod = LogAnalyzerModule()
        logs = "INFO All good\nINFO Loaded\n"
        app, sup = _make_app(logs)

        ai_mock = MagicMock()
        ai_mock.messages = MagicMock()
        ai_mock.messages.create = AsyncMock()

        with patch("anthropic.AsyncAnthropic", return_value=ai_mock):
            await mod.setup(app)

        ctx = _ctx()
        await mod.handle_command("logs", ["analyze"], ctx)
        ai_mock.messages.create.assert_not_awaited()

    async def test_analyze_ai_disabled(self):
        mod = LogAnalyzerModule()
        logs = "ERROR Something failed\n"
        app, sup = _make_app(logs)
        app.config.ai_enabled = False

        ai_mock = MagicMock()
        ai_mock.messages = MagicMock()
        ai_mock.messages.create = AsyncMock()

        with patch("anthropic.AsyncAnthropic", return_value=ai_mock):
            await mod.setup(app)

        ctx = _ctx()
        await mod.handle_command("logs", ["analyze"], ctx)
        ai_mock.messages.create.assert_not_awaited()
        text = ctx.update.message.reply_text.call_args[0][0]
        assert "disabled" in text.lower()
