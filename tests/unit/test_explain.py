"""
Unit tests for ExplainModule.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from app.modules.explain import ExplainModule

_AUTOS = [
    {"id": "abc", "alias": "Turn on lights", "trigger": [], "action": [], "description": ""},
]


def _make_app():
    ha = MagicMock()
    ha.get_automations = AsyncMock(return_value=_AUTOS)
    ha.get_state = AsyncMock(return_value={
        "entity_id": "light.sala", "state": "on",
        "attributes": {"friendly_name": "Sala", "brightness": 200}
    })

    config = MagicMock()
    config.ai_enabled = True
    config.ai_model = "claude-haiku-4-5-20251001"
    config.ai_max_tokens = 512
    config.anthropic_api_key = "test-key"

    discovery = MagicMock()
    discovery.get_all_states = AsyncMock(return_value=[])

    app = MagicMock()
    app.ha_client = ha
    app.config = config
    app.extra = {"discovery": discovery}
    return app, ha


def _ctx():
    ctx = MagicMock()
    ctx.user_id = 1
    ctx.update = MagicMock()
    ctx.update.message = MagicMock()
    ctx.update.message.reply_text = AsyncMock()
    return ctx


def _ai_mock(text="This automation turns on lights at sunrise."):
    ai = MagicMock()
    resp = MagicMock()
    resp.content = [MagicMock(text=text)]
    resp.usage = MagicMock(input_tokens=100, output_tokens=50)
    ai.messages = MagicMock()
    ai.messages.create = AsyncMock(return_value=resp)
    return ai


class TestExplainModule:
    async def test_no_args_shows_usage(self):
        mod = ExplainModule()
        app, _ = _make_app()
        with patch("anthropic.AsyncAnthropic", return_value=_ai_mock()):
            await mod.setup(app)
        ctx = _ctx()
        await mod.handle_command("explain", [], ctx)
        ctx.update.message.reply_text.assert_awaited_once()
        text = ctx.update.message.reply_text.call_args[0][0]
        assert "Usage" in text or "usage" in text

    async def test_explain_automation(self):
        mod = ExplainModule()
        app, ha = _make_app()
        ai = _ai_mock("It turns on lights when the sun rises.")
        with patch("anthropic.AsyncAnthropic", return_value=ai):
            await mod.setup(app)
        ctx = _ctx()
        await mod.handle_command("explain", ["auto", "lights"], ctx)
        ai.messages.create.assert_awaited_once()
        # At least 2 messages: "Explaining..." + explanation
        assert ctx.update.message.reply_text.await_count >= 2

    async def test_explain_entity(self):
        mod = ExplainModule()
        app, ha = _make_app()
        ai = _ai_mock("This is a light entity provided by the MQTT integration.")
        with patch("anthropic.AsyncAnthropic", return_value=ai):
            await mod.setup(app)
        ctx = _ctx()
        await mod.handle_command("explain", ["entity", "light.sala"], ctx)
        ha.get_state.assert_awaited_once_with("light.sala")
        ai.messages.create.assert_awaited_once()

    async def test_explain_integration(self):
        mod = ExplainModule()
        app, _ = _make_app()
        ai = _ai_mock("Zigbee2MQTT bridges Zigbee devices to Home Assistant via MQTT.")
        with patch("anthropic.AsyncAnthropic", return_value=ai):
            await mod.setup(app)
        ctx = _ctx()
        await mod.handle_command("explain", ["integration", "zigbee2mqtt"], ctx)
        ai.messages.create.assert_awaited_once()

    async def test_automation_not_found(self):
        mod = ExplainModule()
        app, _ = _make_app()
        with patch("anthropic.AsyncAnthropic", return_value=_ai_mock()):
            await mod.setup(app)
        ctx = _ctx()
        await mod.handle_command("explain", ["auto", "nonexistent"], ctx)
        text = ctx.update.message.reply_text.call_args[0][0]
        assert "No automation" in text or "nonexistent" in text

    async def test_ai_disabled(self):
        mod = ExplainModule()
        app, _ = _make_app()
        app.config.ai_enabled = False
        ai = _ai_mock()
        with patch("anthropic.AsyncAnthropic", return_value=ai):
            await mod.setup(app)
        ctx = _ctx()
        await mod.handle_command("explain", ["entity", "light.sala"], ctx)
        ai.messages.create.assert_not_awaited()
        text = ctx.update.message.reply_text.call_args_list[-1][0][0]
        assert "disabled" in text.lower()
