"""
Unit tests for AutomationsModule.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
import pytest

from app.modules.automations import AutomationsModule

_AUTOS = [
    {"id": "abc123", "alias": "Turn on lights at sunrise", "mode": "single",
     "trigger": [{"platform": "sun", "event": "sunrise"}],
     "action": [{"service": "light.turn_on"}], "description": ""},
    {"id": "def456", "alias": "Notify on door open", "mode": "single",
     "trigger": [{"platform": "state", "entity_id": "binary_sensor.door"}],
     "action": [{"service": "notify.telegram"}], "description": "ha_copilot"},
]


def _make_app(autos=None):
    ha = MagicMock()
    ha.get_automations = AsyncMock(return_value=autos if autos is not None else _AUTOS)
    ha.call_service = AsyncMock()
    ha.delete_automation = AsyncMock()
    ha.create_automation = AsyncMock(return_value={"id": "new123"})

    config = MagicMock()
    config.ai_enabled = True
    config.ai_model = "claude-haiku-4-5-20251001"
    config.ai_max_tokens = 512
    config.anthropic_api_key = "test"

    pending = MagicMock()
    pending.store = AsyncMock(return_value="act001")

    app = MagicMock()
    app.ha_client = ha
    app.config = config
    app.extra = {"pending_actions": pending}
    return app, ha, pending


def _ctx():
    ctx = MagicMock()
    ctx.user_id = 1
    ctx.chat_id = 1
    ctx.update = MagicMock()
    ctx.update.message = MagicMock()
    ctx.update.message.reply_text = AsyncMock()
    return ctx


class TestAutomationsModule:
    async def test_list(self):
        mod = AutomationsModule()
        app, ha, _ = _make_app()
        await mod.setup(app)
        ctx = _ctx()
        await mod.handle_command("auto", [], ctx)
        ha.get_automations.assert_awaited_once()
        text = ctx.update.message.reply_text.call_args[0][0]
        assert "sunrise" in text

    async def test_list_empty(self):
        mod = AutomationsModule()
        app, ha, _ = _make_app(autos=[])
        await mod.setup(app)
        ctx = _ctx()
        await mod.handle_command("auto", [], ctx)
        ctx.update.message.reply_text.assert_awaited_once()

    async def test_show(self):
        mod = AutomationsModule()
        app, ha, _ = _make_app()
        await mod.setup(app)
        ctx = _ctx()
        await mod.handle_command("auto", ["sunrise", "show"], ctx)
        text = ctx.update.message.reply_text.call_args[0][0]
        assert "abc123" in text

    async def test_on(self):
        mod = AutomationsModule()
        app, ha, _ = _make_app()
        await mod.setup(app)
        await mod.handle_command("auto", ["sunrise", "on"], _ctx())
        ha.call_service.assert_awaited_once()
        args = ha.call_service.call_args[0]
        assert args[1] == "turn_on"

    async def test_off(self):
        mod = AutomationsModule()
        app, ha, _ = _make_app()
        await mod.setup(app)
        await mod.handle_command("auto", ["sunrise", "off"], _ctx())
        ha.call_service.assert_awaited_once()
        args = ha.call_service.call_args[0]
        assert args[1] == "turn_off"

    async def test_trigger(self):
        mod = AutomationsModule()
        app, ha, _ = _make_app()
        await mod.setup(app)
        await mod.handle_command("auto", ["sunrise", "trigger"], _ctx())
        ha.call_service.assert_awaited_once()
        args = ha.call_service.call_args[0]
        assert args[1] == "trigger"

    async def test_delete_requires_confirm(self):
        mod = AutomationsModule()
        app, ha, pending = _make_app()
        await mod.setup(app)
        ctx = _ctx()
        await mod.handle_command("auto", ["sunrise", "delete"], ctx)
        ha.delete_automation.assert_not_awaited()
        # Should have stored pending action
        pending.store.assert_awaited_once()

    async def test_delete_with_confirm_arg(self):
        mod = AutomationsModule()
        app, ha, _ = _make_app()
        await mod.setup(app)
        await mod.handle_command("auto", ["sunrise", "delete", "confirm"], _ctx())
        ha.delete_automation.assert_awaited_once_with("abc123")

    async def test_not_found(self):
        mod = AutomationsModule()
        app, ha, _ = _make_app()
        await mod.setup(app)
        ctx = _ctx()
        await mod.handle_command("auto", ["nonexistent", "on"], ctx)
        ha.call_service.assert_not_awaited()
        text = ctx.update.message.reply_text.call_args[0][0]
        assert "No automation" in text or "nonexistent" in text

    async def test_to_entity_id(self):
        assert AutomationsModule._to_entity_id("Turn on lights") == "automation.turn_on_lights"
        assert AutomationsModule._to_entity_id("Say hello!") == "automation.say_hello"
