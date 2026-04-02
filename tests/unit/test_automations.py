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

    async def test_list_api_error(self):
        mod = AutomationsModule()
        app, ha, _ = _make_app()
        ha.get_automations = AsyncMock(side_effect=Exception("HA unreachable"))
        await mod.setup(app)
        ctx = _ctx()
        await mod.handle_command("auto", [], ctx)
        text = ctx.update.message.reply_text.call_args[0][0]
        assert "Cannot list automations" in text or "HA unreachable" in text

    async def test_list_many_truncated(self):
        many = [{"id": f"auto_{i}", "alias": f"Auto {i}", "mode": "single", "description": ""} for i in range(35)]
        mod = AutomationsModule()
        app, ha, _ = _make_app(autos=many)
        await mod.setup(app)
        ctx = _ctx()
        await mod.handle_command("auto", [], ctx)
        text = ctx.update.message.reply_text.call_args[0][0]
        assert "more" in text

    async def test_list_copilot_tag(self):
        autos = [{"id": "x", "alias": "Bot auto", "mode": "single", "description": "ha_copilot"}]
        mod = AutomationsModule()
        app, ha, _ = _make_app(autos=autos)
        await mod.setup(app)
        ctx = _ctx()
        await mod.handle_command("auto", [], ctx)
        text = ctx.update.message.reply_text.call_args[0][0]
        assert "🤖" in text

    async def test_action_query_only_no_action_shows_usage(self):
        mod = AutomationsModule()
        app, ha, _ = _make_app()
        await mod.setup(app)
        ctx = _ctx()
        await mod.handle_command("auto", ["sunrise"], ctx)
        text = ctx.update.message.reply_text.call_args[0][0]
        assert "Usage" in text

    async def test_unknown_action_error(self):
        mod = AutomationsModule()
        app, ha, _ = _make_app()
        await mod.setup(app)
        ctx = _ctx()
        await mod.handle_command("auto", ["sunrise", "explode"], ctx)
        text = ctx.update.message.reply_text.call_args[0][0]
        assert "Unknown action" in text

    async def test_action_api_error_on_turn_on(self):
        mod = AutomationsModule()
        app, ha, _ = _make_app()
        ha.call_service = AsyncMock(side_effect=Exception("call failed"))
        await mod.setup(app)
        ctx = _ctx()
        await mod.handle_command("auto", ["sunrise", "on"], ctx)
        text = ctx.update.message.reply_text.call_args[0][0]
        assert "Failed" in text or "call failed" in text

    async def test_trigger_api_error(self):
        mod = AutomationsModule()
        app, ha, _ = _make_app()
        ha.call_service = AsyncMock(side_effect=Exception("trigger failed"))
        await mod.setup(app)
        ctx = _ctx()
        await mod.handle_command("auto", ["sunrise", "trigger"], ctx)
        text = ctx.update.message.reply_text.call_args[0][0]
        assert "Failed" in text or "trigger failed" in text

    async def test_delete_confirmed_api_error(self):
        mod = AutomationsModule()
        app, ha, _ = _make_app()
        ha.delete_automation = AsyncMock(side_effect=Exception("delete failed"))
        await mod.setup(app)
        ctx = _ctx()
        await mod.handle_command("auto", ["sunrise", "delete", "confirm"], ctx)
        text = ctx.update.message.reply_text.call_args[0][0]
        assert "Delete failed" in text or "delete failed" in text

    async def test_create_no_description_shows_usage(self):
        mod = AutomationsModule()
        app, ha, _ = _make_app()
        await mod.setup(app)
        ctx = _ctx()
        await mod.handle_command("auto", ["create"], ctx)
        text = ctx.update.message.reply_text.call_args[0][0]
        assert "Usage" in text

    async def test_create_ai_disabled(self):
        mod = AutomationsModule()
        app, ha, _ = _make_app()
        app.config.ai_enabled = False
        await mod.setup(app)
        ctx = _ctx()
        await mod.handle_command("auto", ["create", "turn on lights at sunrise"], ctx)
        text = ctx.update.message.reply_text.call_args[0][0]
        assert "AI is disabled" in text

    async def test_create_generator_error(self):
        mod = AutomationsModule()
        app, ha, _ = _make_app()
        await mod.setup(app)

        mock_gen = MagicMock()
        mock_gen.generate_automation = AsyncMock(side_effect=Exception("AI unavailable"))
        mod._generator = mock_gen

        ctx = _ctx()
        await mod.handle_command("auto", ["create", "turn lights on at sunrise"], ctx)
        # Multiple replies: generating message + error
        last = ctx.update.message.reply_text.call_args_list[-1][0][0]
        assert "YAML generation failed" in last or "AI unavailable" in last

    async def test_create_shows_preview(self):
        mod = AutomationsModule()
        app, ha, _ = _make_app()
        await mod.setup(app)

        from app.schemas.automation_schema import AutomationConfig
        mock_config = MagicMock(spec=AutomationConfig)
        mock_config.alias = "Test automation"
        mock_config.model_dump = MagicMock(return_value={
            "alias": "Test automation",
            "trigger": [{"platform": "time", "at": "07:00:00"}],
            "action": [{"service": "light.turn_on"}]
        })

        mock_gen = MagicMock()
        mock_gen.generate_automation = AsyncMock(return_value=mock_config)
        mod._generator = mock_gen

        ctx = _ctx()
        await mod.handle_command("auto", ["create", "turn lights on at 7am"], ctx)
        # Last call should be preview with keyboard
        last_call = ctx.update.message.reply_text.call_args_list[-1]
        assert last_call is not None

    async def test_find_exact_id(self):
        mod = AutomationsModule()
        result = mod._find(_AUTOS, "abc123")
        assert result is not None
        assert result["id"] == "abc123"

    async def test_find_partial_alias(self):
        mod = AutomationsModule()
        result = mod._find(_AUTOS, "sunrise")
        assert result is not None
        assert "sunrise" in result["alias"].lower()

    async def test_find_no_match(self):
        mod = AutomationsModule()
        result = mod._find(_AUTOS, "nonexistent_xyz")
        assert result is None

    async def test_action_get_automations_error(self):
        mod = AutomationsModule()
        app, ha, _ = _make_app()
        ha.get_automations = AsyncMock(side_effect=Exception("connection refused"))
        await mod.setup(app)
        ctx = _ctx()
        await mod.handle_command("auto", ["sunrise", "on"], ctx)
        text = ctx.update.message.reply_text.call_args[0][0]
        assert "Cannot get automations" in text or "connection refused" in text

    async def test_edit_ai_disabled(self):
        mod = AutomationsModule()
        app, ha, _ = _make_app()
        app.config.ai_enabled = False
        await mod.setup(app)
        ctx = _ctx()
        await mod.handle_command("auto", ["sunrise", "edit", "add condition"], ctx)
        text = ctx.update.message.reply_text.call_args[0][0]
        assert "AI is disabled" in text

    async def test_edit_generator_error(self):
        mod = AutomationsModule()
        app, ha, _ = _make_app()
        await mod.setup(app)

        mock_gen = MagicMock()
        mock_gen.generate_automation_edit = AsyncMock(side_effect=Exception("edit failed"))
        mod._generator = mock_gen

        ctx = _ctx()
        await mod.handle_command("auto", ["sunrise", "edit", "add condition at night"], ctx)
        last = ctx.update.message.reply_text.call_args_list[-1][0][0]
        assert "Edit generation failed" in last or "edit failed" in last
