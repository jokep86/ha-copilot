"""
Unit tests for ScenesModule.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from app.modules.scenes import ScenesModule


def _make_app(scenes=None, ai_enabled=True):
    ha = MagicMock()
    ha.get_scenes = AsyncMock(return_value=scenes or [])
    ha.call_service = AsyncMock()
    ha.delete_scene = AsyncMock()
    ha.create_scene = AsyncMock()

    config = MagicMock()
    config.ai_enabled = ai_enabled

    app = MagicMock()
    app.ha_client = ha
    app.config = config
    app.extra = {}
    return app, ha, config


def _make_context():
    ctx = MagicMock()
    ctx.update = MagicMock()
    ctx.update.message = MagicMock()
    ctx.update.message.reply_text = AsyncMock()
    ctx.user_id = 12345
    ctx.telegram_context = None
    return ctx


class TestScenesModule:
    async def test_setup_stores_ha(self):
        mod = ScenesModule()
        app, ha, _ = _make_app()
        await mod.setup(app)
        assert mod._ha is ha

    async def test_teardown_is_noop(self):
        mod = ScenesModule()
        app, _, _ = _make_app()
        await mod.setup(app)
        await mod.teardown()

    async def test_module_attributes(self):
        mod = ScenesModule()
        assert "scenes" in mod.commands
        assert "scene" in mod.commands
        assert mod.name == "scenes"

    async def test_cmd_list_shows_scenes(self):
        scenes = [
            {"id": "morning", "name": "Morning"},
            {"id": "evening", "name": "Evening"},
        ]
        mod = ScenesModule()
        app, ha, _ = _make_app(scenes=scenes)
        await mod.setup(app)
        ctx = _make_context()
        await mod.handle_command("scenes", [], ctx)
        ctx.update.message.reply_text.assert_awaited_once()
        text = ctx.update.message.reply_text.call_args[0][0]
        assert "Morning" in text
        assert "Evening" in text

    async def test_cmd_list_no_scenes(self):
        mod = ScenesModule()
        app, ha, _ = _make_app(scenes=[])
        await mod.setup(app)
        ctx = _make_context()
        await mod.handle_command("scenes", [], ctx)
        text = ctx.update.message.reply_text.call_args[0][0]
        assert "No scenes" in text

    async def test_cmd_list_api_error(self):
        mod = ScenesModule()
        app, ha, _ = _make_app()
        ha.get_scenes = AsyncMock(side_effect=Exception("HA unreachable"))
        await mod.setup(app)
        ctx = _make_context()
        await mod.handle_command("scenes", [], ctx)
        text = ctx.update.message.reply_text.call_args[0][0]
        assert "Cannot list scenes" in text or "HA unreachable" in text

    async def test_cmd_list_many_scenes_truncated(self):
        scenes = [{"id": f"scene_{i}", "name": f"Scene {i}"} for i in range(40)]
        mod = ScenesModule()
        app, ha, _ = _make_app(scenes=scenes)
        await mod.setup(app)
        ctx = _make_context()
        await mod.handle_command("scenes", [], ctx)
        text = ctx.update.message.reply_text.call_args[0][0]
        assert "more" in text  # truncation message

    async def test_handle_command_no_args_shows_list(self):
        scenes = [{"id": "night", "name": "Night"}]
        mod = ScenesModule()
        app, ha, _ = _make_app(scenes=scenes)
        await mod.setup(app)
        ctx = _make_context()
        # /scene with no args should list
        await mod.handle_command("scene", [], ctx)
        ctx.update.message.reply_text.assert_awaited_once()

    async def test_handle_command_usage_hint(self):
        mod = ScenesModule()
        app, ha, _ = _make_app(scenes=[{"id": "night", "name": "Night"}])
        await mod.setup(app)
        ctx = _make_context()
        # /scene <query> alone — no action
        await mod.handle_command("scene", ["night"], ctx)
        text = ctx.update.message.reply_text.call_args[0][0]
        assert "Usage" in text

    async def test_cmd_activate_success(self):
        scenes = [{"id": "morning", "name": "Morning"}]
        mod = ScenesModule()
        app, ha, _ = _make_app(scenes=scenes)
        await mod.setup(app)
        ctx = _make_context()
        await mod.handle_command("scene", ["morning", "activate"], ctx)
        ha.call_service.assert_awaited_once_with(
            "scene", "turn_on", {"entity_id": "scene.morning"}
        )
        text = ctx.update.message.reply_text.call_args[0][0]
        assert "activated" in text

    async def test_cmd_activate_not_found(self):
        scenes = [{"id": "morning", "name": "Morning"}]
        mod = ScenesModule()
        app, ha, _ = _make_app(scenes=scenes)
        await mod.setup(app)
        ctx = _make_context()
        await mod.handle_command("scene", ["nonexistent", "activate"], ctx)
        text = ctx.update.message.reply_text.call_args[0][0]
        assert "No scene" in text

    async def test_cmd_activate_api_error(self):
        scenes = [{"id": "morning", "name": "Morning"}]
        mod = ScenesModule()
        app, ha, _ = _make_app(scenes=scenes)
        ha.call_service = AsyncMock(side_effect=Exception("service call failed"))
        await mod.setup(app)
        ctx = _make_context()
        await mod.handle_command("scene", ["morning", "activate"], ctx)
        text = ctx.update.message.reply_text.call_args[0][0]
        assert "Activation failed" in text or "service call failed" in text

    async def test_cmd_delete_with_confirm(self):
        scenes = [{"id": "morning", "name": "Morning"}]
        mod = ScenesModule()
        app, ha, _ = _make_app(scenes=scenes)
        await mod.setup(app)
        ctx = _make_context()
        await mod.handle_command("scene", ["morning", "delete", "confirm"], ctx)
        ha.delete_scene.assert_awaited_once_with("morning")
        text = ctx.update.message.reply_text.call_args[0][0]
        assert "deleted" in text

    async def test_cmd_delete_without_confirm_shows_prompt(self):
        scenes = [{"id": "morning", "name": "Morning"}]
        mod = ScenesModule()
        app, ha, _ = _make_app(scenes=scenes)
        await mod.setup(app)
        ctx = _make_context()
        await mod.handle_command("scene", ["morning", "delete"], ctx)
        ha.delete_scene.assert_not_awaited()
        text = ctx.update.message.reply_text.call_args[0][0]
        # Should ask for confirmation
        assert "Delete" in text or "confirm" in text

    async def test_cmd_delete_api_error(self):
        scenes = [{"id": "morning", "name": "Morning"}]
        mod = ScenesModule()
        app, ha, _ = _make_app(scenes=scenes)
        ha.delete_scene = AsyncMock(side_effect=Exception("delete failed"))
        await mod.setup(app)
        ctx = _make_context()
        await mod.handle_command("scene", ["morning", "delete", "confirm"], ctx)
        text = ctx.update.message.reply_text.call_args[0][0]
        assert "Delete failed" in text or "delete failed" in text

    async def test_cmd_unknown_action(self):
        scenes = [{"id": "morning", "name": "Morning"}]
        mod = ScenesModule()
        app, ha, _ = _make_app(scenes=scenes)
        await mod.setup(app)
        ctx = _make_context()
        await mod.handle_command("scene", ["morning", "explode"], ctx)
        text = ctx.update.message.reply_text.call_args[0][0]
        assert "Unknown action" in text or "activate" in text

    async def test_cmd_create_no_description(self):
        mod = ScenesModule()
        app, ha, _ = _make_app()
        await mod.setup(app)
        ctx = _make_context()
        await mod.handle_command("scene", ["create"], ctx)
        text = ctx.update.message.reply_text.call_args[0][0]
        assert "Usage" in text

    async def test_cmd_create_ai_disabled(self):
        mod = ScenesModule()
        app, ha, _ = _make_app(ai_enabled=False)
        await mod.setup(app)
        ctx = _make_context()
        await mod.handle_command("scene", ["create", "cozy", "evening"], ctx)
        text = ctx.update.message.reply_text.call_args[0][0]
        assert "AI is disabled" in text or "ai_enabled" in text

    async def test_find_by_exact_id(self):
        mod = ScenesModule()
        scenes = [{"id": "morning", "name": "Morning Sun"}, {"id": "eve", "name": "Evening"}]
        result = mod._find(scenes, "morning")
        assert result is not None
        assert result["id"] == "morning"

    async def test_find_by_partial_name(self):
        mod = ScenesModule()
        scenes = [{"id": "morning", "name": "Morning Sun"}, {"id": "eve", "name": "Evening"}]
        result = mod._find(scenes, "morning sun")
        assert result is not None
        assert result["id"] == "morning"

    async def test_find_no_match(self):
        mod = ScenesModule()
        scenes = [{"id": "morning", "name": "Morning"}]
        result = mod._find(scenes, "nonexistent")
        assert result is None

    async def test_cmd_create_generator_error(self):
        mod = ScenesModule()
        app, ha, _ = _make_app()
        await mod.setup(app)

        mock_generator = MagicMock()
        mock_generator.generate_scene = AsyncMock(side_effect=Exception("AI unavailable"))
        mod._generator = mock_generator

        ctx = _make_context()
        await mod.handle_command("scene", ["create", "cozy evening"], ctx)
        # Should send an error response; we may get multiple calls (generating message + error)
        assert ctx.update.message.reply_text.await_count >= 1
        last_text = ctx.update.message.reply_text.call_args_list[-1][0][0]
        assert "YAML generation failed" in last_text or "AI unavailable" in last_text
