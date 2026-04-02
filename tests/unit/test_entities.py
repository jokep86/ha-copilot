"""
Unit tests for EntitiesModule.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
import pytest

from app.modules.entities import EntitiesModule


def _make_app(entities=None, history=None):
    ha = MagicMock()
    ha.get_history = AsyncMock(return_value=history or [])

    discovery = MagicMock()
    discovery.get_all_states = AsyncMock(return_value=entities or [])
    discovery.get_entities_by_domain = AsyncMock(return_value=entities or [])
    discovery.resolve_entity_id = AsyncMock(return_value=("sensor.temp", None))

    app = MagicMock()
    app.ha_client = ha
    app.extra = {"discovery": discovery}
    return app, ha, discovery


def _make_context(page=0):
    ctx = MagicMock()
    ctx.telegram_context = MagicMock()
    ctx.telegram_context.user_data = {"current_page": page}
    ctx.update = MagicMock()
    ctx.update.message = MagicMock()
    ctx.update.message.reply_text = AsyncMock()
    ctx.user_id = 12345
    return ctx


class TestEntitiesModule:
    async def test_setup_stores_references(self):
        mod = EntitiesModule()
        app, ha, discovery = _make_app()
        await mod.setup(app)
        assert mod._ha is ha
        assert mod._discovery is discovery

    async def test_teardown_is_noop(self):
        mod = EntitiesModule()
        app, _, _ = _make_app()
        await mod.setup(app)
        await mod.teardown()  # should not raise

    async def test_cmd_entities_all_no_filter(self):
        entities = [
            {"entity_id": "light.sala", "state": "on", "attributes": {"friendly_name": "Sala"}},
            {"entity_id": "switch.fan", "state": "off", "attributes": {}},
        ]
        mod = EntitiesModule()
        app, ha, discovery = _make_app(entities=entities)
        await mod.setup(app)
        ctx = _make_context()
        await mod.handle_command("entities", [], ctx)
        ctx.update.message.reply_text.assert_awaited_once()
        text = ctx.update.message.reply_text.call_args[0][0]
        assert "Sala" in text  # friendly_name shown
        assert "All entities" in text

    async def test_cmd_entities_by_domain(self):
        entities = [
            {"entity_id": "sensor.temp", "state": "22", "attributes": {"unit_of_measurement": "°C"}},
        ]
        mod = EntitiesModule()
        app, ha, discovery = _make_app(entities=entities)
        await mod.setup(app)
        ctx = _make_context()
        await mod.handle_command("entities", ["sensor"], ctx)
        discovery.get_entities_by_domain.assert_awaited_once_with("sensor")
        text = ctx.update.message.reply_text.call_args[0][0]
        assert "sensor entities" in text

    async def test_cmd_entities_empty_result(self):
        mod = EntitiesModule()
        app, ha, discovery = _make_app(entities=[])
        await mod.setup(app)
        ctx = _make_context()
        await mod.handle_command("entities", ["light"], ctx)
        ctx.update.message.reply_text.assert_awaited_once()

    async def test_cmd_entities_no_discovery(self):
        mod = EntitiesModule()
        app, _, _ = _make_app()
        app.extra = {}  # no discovery
        await mod.setup(app)
        ctx = _make_context()
        await mod.handle_command("entities", [], ctx)
        ctx.update.message.reply_text.assert_awaited_once()
        text = ctx.update.message.reply_text.call_args[0][0]
        assert "Discovery" in text or "not available" in text

    async def test_cmd_history_no_args(self):
        mod = EntitiesModule()
        app, _, _ = _make_app()
        await mod.setup(app)
        ctx = _make_context()
        await mod.handle_command("history", [], ctx)
        ctx.update.message.reply_text.assert_awaited_once()
        text = ctx.update.message.reply_text.call_args[0][0]
        assert "Usage" in text

    async def test_cmd_history_entity_not_found(self):
        mod = EntitiesModule()
        app, ha, discovery = _make_app()
        discovery.resolve_entity_id = AsyncMock(return_value=(None, "Entity not found"))
        await mod.setup(app)
        ctx = _make_context()
        await mod.handle_command("history", ["nonexistent"], ctx)
        text = ctx.update.message.reply_text.call_args[0][0]
        assert "Entity not found" in text

    async def test_cmd_history_with_data(self):
        history_data = [[
            {"state": "on", "last_changed": "2026-01-01T10:00:00Z"},
            {"state": "off", "last_changed": "2026-01-01T11:00:00Z"},
            {"state": "on", "last_changed": "2026-01-01T12:00:00Z"},
        ]]
        mod = EntitiesModule()
        app, ha, discovery = _make_app(history=history_data)
        await mod.setup(app)
        ctx = _make_context()
        await mod.handle_command("history", ["sensor.temp"], ctx)
        text = ctx.update.message.reply_text.call_args[0][0]
        assert "History" in text  # header present

    async def test_cmd_history_custom_hours(self):
        history_data = [[{"state": "22", "last_changed": "2026-01-01T10:00:00Z"}]]
        mod = EntitiesModule()
        app, ha, discovery = _make_app(history=history_data)
        await mod.setup(app)
        ctx = _make_context()
        await mod.handle_command("history", ["sensor.temp", "48"], ctx)
        ha.get_history.assert_awaited_once_with("sensor.temp", hours=48)

    async def test_cmd_history_invalid_hours_defaults(self):
        history_data = [[{"state": "22", "last_changed": "2026-01-01T10:00:00Z"}]]
        mod = EntitiesModule()
        app, ha, discovery = _make_app(history=history_data)
        await mod.setup(app)
        ctx = _make_context()
        await mod.handle_command("history", ["sensor.temp", "notanumber"], ctx)
        # Should use default 24h
        ha.get_history.assert_awaited_once_with("sensor.temp", hours=24)

    async def test_cmd_history_hours_clamped_min(self):
        history_data = [[{"state": "22", "last_changed": "2026-01-01T10:00:00Z"}]]
        mod = EntitiesModule()
        app, ha, discovery = _make_app(history=history_data)
        await mod.setup(app)
        ctx = _make_context()
        await mod.handle_command("history", ["sensor.temp", "0"], ctx)
        ha.get_history.assert_awaited_once_with("sensor.temp", hours=1)

    async def test_cmd_history_hours_clamped_max(self):
        history_data = [[{"state": "22", "last_changed": "2026-01-01T10:00:00Z"}]]
        mod = EntitiesModule()
        app, ha, discovery = _make_app(history=history_data)
        await mod.setup(app)
        ctx = _make_context()
        await mod.handle_command("history", ["sensor.temp", "9999"], ctx)
        ha.get_history.assert_awaited_once_with("sensor.temp", hours=168)

    async def test_cmd_history_empty_result(self):
        mod = EntitiesModule()
        app, ha, discovery = _make_app(history=[])
        await mod.setup(app)
        ctx = _make_context()
        await mod.handle_command("history", ["sensor.temp"], ctx)
        text = ctx.update.message.reply_text.call_args[0][0]
        assert "No history" in text

    async def test_cmd_history_api_error(self):
        mod = EntitiesModule()
        app, ha, discovery = _make_app()
        ha.get_history = AsyncMock(side_effect=Exception("connection refused"))
        await mod.setup(app)
        ctx = _make_context()
        await mod.handle_command("history", ["sensor.temp"], ctx)
        text = ctx.update.message.reply_text.call_args[0][0]
        assert "Cannot get history" in text or "connection refused" in text

    async def test_module_attributes(self):
        mod = EntitiesModule()
        assert "entities" in mod.commands
        assert "history" in mod.commands
        assert mod.name == "entities"
