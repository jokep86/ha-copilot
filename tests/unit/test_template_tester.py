"""
Unit tests for TemplateTesterModule.
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from app.modules.template_tester import TemplateTesterModule, WATCH_INTERVAL, WATCH_DURATION


def _make_app(render_result="22.5"):
    ha = MagicMock()
    ha.render_template = AsyncMock(return_value=render_result)

    app = MagicMock()
    app.ha_client = ha
    return app, ha


def _make_context():
    ctx = MagicMock()
    ctx.update = MagicMock()
    ctx.update.message = MagicMock()
    ctx.update.message.reply_text = AsyncMock()
    ctx.user_id = 12345
    return ctx


class TestTemplateTesterModule:
    async def test_setup_stores_ha(self):
        mod = TemplateTesterModule()
        app, ha = _make_app()
        await mod.setup(app)
        assert mod._ha is ha

    async def test_teardown_is_noop(self):
        mod = TemplateTesterModule()
        app, _ = _make_app()
        await mod.setup(app)
        await mod.teardown()

    async def test_module_attributes(self):
        mod = TemplateTesterModule()
        assert "template" in mod.commands
        assert mod.name == "template_tester"

    async def test_no_args_shows_usage(self):
        mod = TemplateTesterModule()
        app, _ = _make_app()
        await mod.setup(app)
        ctx = _make_context()
        await mod.handle_command("template", [], ctx)
        text = ctx.update.message.reply_text.call_args[0][0]
        assert "Usage" in text or "Template Tester" in text

    async def test_empty_template_error(self):
        mod = TemplateTesterModule()
        app, _ = _make_app()
        await mod.setup(app)
        ctx = _make_context()
        await mod.handle_command("template", ["watch"], ctx)
        text = ctx.update.message.reply_text.call_args[0][0]
        assert "Empty template" in text

    async def test_evaluate_simple_template(self):
        mod = TemplateTesterModule()
        app, ha = _make_app(render_result="22.5")
        await mod.setup(app)
        ctx = _make_context()
        await mod.handle_command("template", ['{{ states("sensor.temp") }}'], ctx)
        ha.render_template.assert_awaited_once_with('{{ states("sensor.temp") }}')
        text = ctx.update.message.reply_text.call_args[0][0]
        assert "22.5" in text or "Result" in text

    async def test_evaluate_template_error(self):
        mod = TemplateTesterModule()
        app, ha = _make_app()
        ha.render_template = AsyncMock(side_effect=Exception("Template error: unknown variable"))
        await mod.setup(app)
        ctx = _make_context()
        await mod.handle_command("template", ['{{ invalid }}'], ctx)
        text = ctx.update.message.reply_text.call_args[0][0]
        assert "Template error" in text or "unknown variable" in text

    async def test_evaluate_multi_word_template(self):
        mod = TemplateTesterModule()
        app, ha = _make_app(render_result="on")
        await mod.setup(app)
        ctx = _make_context()
        await mod.handle_command("template", ["{{", "states('light.sala')", "}}"], ctx)
        ha.render_template.assert_awaited_once_with("{{ states('light.sala') }}")
        text = ctx.update.message.reply_text.call_args[0][0]
        assert "on" in text

    async def test_watch_mode_sends_initial_message(self):
        mod = TemplateTesterModule()
        app, ha = _make_app(render_result="22.5")
        await mod.setup(app)
        ctx = _make_context()

        # Mock the message returned from reply_text (for edit_text)
        mock_msg = MagicMock()
        mock_msg.edit_text = AsyncMock()
        ctx.update.message.reply_text = AsyncMock(return_value=mock_msg)

        # Patch asyncio.sleep to avoid waiting, and limit iterations
        call_count = 0
        async def fast_sleep(seconds):
            nonlocal call_count
            call_count += 1
            if call_count > 2:
                raise asyncio.CancelledError()

        with patch("app.modules.template_tester.WATCH_DURATION", 10), \
             patch("app.modules.template_tester.WATCH_INTERVAL", 5), \
             patch("asyncio.sleep", fast_sleep):
            try:
                await mod.handle_command("template", ["watch", '{{ states("sensor.temp") }}'], ctx)
            except asyncio.CancelledError:
                pass

        ctx.update.message.reply_text.assert_awaited_once()
        initial_text = ctx.update.message.reply_text.call_args[0][0]
        assert "Watch" in initial_text

    async def test_watch_initial_template_error(self):
        mod = TemplateTesterModule()
        app, ha = _make_app()
        ha.render_template = AsyncMock(side_effect=Exception("parse error"))
        await mod.setup(app)
        ctx = _make_context()
        await mod.handle_command("template", ["watch", '{{ bad }}'], ctx)
        text = ctx.update.message.reply_text.call_args[0][0]
        assert "Template error" in text or "parse error" in text

    async def test_format_watch_normal(self):
        mod = TemplateTesterModule()
        text = mod._format_watch("{{ states('x') }}", "on", iteration=3, done=False)
        assert "Watch" in text
        assert "on" in text

    async def test_format_watch_done(self):
        mod = TemplateTesterModule()
        text = mod._format_watch("{{ states('x') }}", "on", iteration=12, done=True)
        assert "done" in text

    async def test_format_watch_long_template_truncated(self):
        mod = TemplateTesterModule()
        long_template = "{{ states('sensor." + "x" * 100 + "') }}"
        text = mod._format_watch(long_template, "22", iteration=1)
        assert "…" in text
