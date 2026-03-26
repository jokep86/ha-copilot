"""
Unit tests for QuickActionsModule and fuzzy entity discovery.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
import pytest

from app.modules.quick_actions import QuickActionsModule
from app.config import QuickActionConfig, QuickActionStep


def _qa(name="Good Morning", service="light.turn_on", target=None):
    return QuickActionConfig(
        name=name,
        actions=[QuickActionStep(service=service, target=target or {"entity_id": "light.sala"})],
    )


def _app(quick_actions=None):
    app = MagicMock()
    app.config.quick_actions = quick_actions if quick_actions is not None else [_qa()]
    app.ha_client.call_service = AsyncMock(return_value={})
    return app


def _context():
    ctx = MagicMock()
    ctx.update.message.reply_text = AsyncMock()
    return ctx


class TestQuickActionsModule:
    def test_commands(self):
        assert "quick" in QuickActionsModule.commands

    async def test_no_quick_actions_configured(self):
        m = QuickActionsModule()
        await m.setup(_app(quick_actions=[]))
        ctx = _context()
        await m.handle_command("quick", [], ctx)
        text = ctx.update.message.reply_text.call_args[0][0]
        assert "no quick actions" in text.lower()

    async def test_show_keyboard(self):
        actions = [_qa("Morning"), _qa("Evening"), _qa("All Off", "light.turn_off")]
        m = QuickActionsModule()
        await m.setup(_app(quick_actions=actions))
        ctx = _context()
        await m.handle_command("quick", [], ctx)
        ctx.update.message.reply_text.assert_called_once()
        # Should pass reply_markup (InlineKeyboardMarkup)
        call_kwargs = ctx.update.message.reply_text.call_args[1]
        assert "reply_markup" in call_kwargs

    async def test_execute_by_name_success(self):
        m = QuickActionsModule()
        app = _app()
        await m.setup(app)
        ctx = _context()
        await m.handle_command("quick", ["Good", "Morning"], ctx)
        app.ha_client.call_service.assert_called_once_with(
            "light", "turn_on", {"entity_id": "light.sala"}
        )
        text = ctx.update.message.reply_text.call_args[0][0]
        assert "executed" in text.lower()

    async def test_execute_by_name_not_found(self):
        m = QuickActionsModule()
        await m.setup(_app())
        ctx = _context()
        await m.handle_command("quick", ["Nonexistent"], ctx)
        text = ctx.update.message.reply_text.call_args[0][0]
        assert "not found" in text.lower()

    async def test_execute_partial_failure(self):
        m = QuickActionsModule()
        app = _app()
        app.ha_client.call_service = AsyncMock(side_effect=Exception("service error"))
        await m.setup(app)
        ctx = _context()
        await m.handle_command("quick", ["Good Morning"], ctx)
        text = ctx.update.message.reply_text.call_args[0][0]
        assert "partial" in text.lower() or "failure" in text.lower() or "service error" in text.lower()

    async def test_multiple_steps_executed(self):
        qa = QuickActionConfig(
            name="Combo",
            actions=[
                QuickActionStep(service="light.turn_on", target={"entity_id": "light.a"}),
                QuickActionStep(service="switch.turn_off", target={"entity_id": "switch.b"}),
            ],
        )
        m = QuickActionsModule()
        app = _app(quick_actions=[qa])
        await m.setup(app)
        ctx = _context()
        await m.handle_command("quick", ["Combo"], ctx)
        assert app.ha_client.call_service.call_count == 2


class TestFuzzyEntityDiscovery:
    """Tests for the fuzzy matching in EntityDiscovery.find_entity."""

    def _make_states(self):
        return [
            {"entity_id": "light.living_room", "state": "on", "attributes": {"friendly_name": "Living Room Light"}},
            {"entity_id": "sensor.temperature", "state": "22", "attributes": {"friendly_name": "Temperature Sensor"}},
            {"entity_id": "switch.garden", "state": "off", "attributes": {"friendly_name": "Garden Switch"}},
        ]

    async def test_exact_substring_match(self):
        from app.ha.discovery import EntityDiscovery

        ha = MagicMock()
        ha.get_states = AsyncMock(return_value=self._make_states())
        d = EntityDiscovery(ha)
        results = await d.find_entity("living")
        assert any(r["entity_id"] == "light.living_room" for r in results)

    async def test_fuzzy_typo_tolerance(self):
        from app.ha.discovery import EntityDiscovery

        ha = MagicMock()
        ha.get_states = AsyncMock(return_value=self._make_states())
        d = EntityDiscovery(ha)
        # "livng room" is close enough to "Living Room Light"
        results = await d.find_entity("living room light", fuzzy=True)
        assert len(results) > 0
        assert any(r["entity_id"] == "light.living_room" for r in results)

    async def test_no_match_returns_empty(self):
        from app.ha.discovery import EntityDiscovery

        ha = MagicMock()
        ha.get_states = AsyncMock(return_value=self._make_states())
        d = EntityDiscovery(ha)
        results = await d.find_entity("xxxxxxunknownxxxxxx", fuzzy=True)
        assert results == []

    async def test_domain_filter_applied(self):
        from app.ha.discovery import EntityDiscovery

        ha = MagicMock()
        ha.get_states = AsyncMock(return_value=self._make_states())
        d = EntityDiscovery(ha)
        results = await d.find_entity("room", domain="sensor")
        # "living_room" is a light not a sensor — should be excluded
        assert all(r["entity_id"].startswith("sensor.") for r in results)


class TestResolveEntityId:
    """Tests for EntityDiscovery.resolve_entity_id."""

    def _make_states(self):
        return [
            {"entity_id": "light.living_room", "state": "on", "attributes": {"friendly_name": "Living Room Light"}},
            {"entity_id": "sensor.temperature", "state": "22", "attributes": {"friendly_name": "Temperature Sensor"}},
        ]

    async def test_exact_entity_id_match(self):
        from app.ha.discovery import EntityDiscovery
        ha = MagicMock()
        ha.get_states = AsyncMock(return_value=self._make_states())
        d = EntityDiscovery(ha)
        eid, err = await d.resolve_entity_id("light.living_room")
        assert eid == "light.living_room"
        assert err is None

    async def test_fuzzy_friendly_name_match(self):
        from app.ha.discovery import EntityDiscovery
        ha = MagicMock()
        ha.get_states = AsyncMock(return_value=self._make_states())
        d = EntityDiscovery(ha)
        eid, err = await d.resolve_entity_id("living room light")
        assert eid == "light.living_room"
        assert err is None

    async def test_no_match_returns_error(self):
        from app.ha.discovery import EntityDiscovery
        ha = MagicMock()
        ha.get_states = AsyncMock(return_value=self._make_states())
        d = EntityDiscovery(ha)
        eid, err = await d.resolve_entity_id("xxxxxnomatchxxxxx")
        assert eid is None
        assert err is not None
        assert "xxxxxnomatchxxxxx" in err

    async def test_partial_entity_id_match(self):
        from app.ha.discovery import EntityDiscovery
        ha = MagicMock()
        ha.get_states = AsyncMock(return_value=self._make_states())
        d = EntityDiscovery(ha)
        eid, err = await d.resolve_entity_id("temperature")
        assert eid == "sensor.temperature"
        assert err is None
