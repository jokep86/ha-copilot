"""
Unit tests for DevicesModule.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from app.modules.devices import DevicesModule


def _make_app(entities: list | None = None, domains: dict | None = None):
    ha = MagicMock()
    ha.get_state = AsyncMock(return_value={"state": "off", "attributes": {"friendly_name": "Sala"}})
    ha.call_service = AsyncMock()

    discovery = MagicMock()
    discovery.get_entities_by_domain = AsyncMock(return_value=entities or [])
    discovery.get_domains = AsyncMock(return_value=domains or {"light": 3, "switch": 2})

    app = MagicMock()
    app.ha_client = ha
    app.extra = {"discovery": discovery}
    app.config = MagicMock()
    return app, ha, discovery


def _make_context():
    ctx = MagicMock()
    ctx.telegram_context = MagicMock()
    ctx.telegram_context.user_data = {"current_page": 0}
    ctx.update = MagicMock()
    ctx.update.message = MagicMock()
    ctx.update.message.reply_text = AsyncMock()
    return ctx


class TestDevicesModule:
    async def test_setup_stores_ha_and_discovery(self):
        mod = DevicesModule()
        app, ha, discovery = _make_app()
        await mod.setup(app)
        assert mod._ha is ha
        assert mod._discovery is discovery

    async def test_cmd_devices_no_domain_sends_summary(self):
        mod = DevicesModule()
        app, ha, discovery = _make_app(domains={"light": 5, "switch": 2})
        await mod.setup(app)
        ctx = _make_context()
        await mod.handle_command("devices", [], ctx)
        ctx.update.message.reply_text.assert_awaited_once()
        text = ctx.update.message.reply_text.call_args[0][0]
        assert "light" in text

    async def test_cmd_devices_with_domain_sends_list(self):
        mod = DevicesModule()
        entities = [
            {"entity_id": "light.sala", "state": "on", "attributes": {"friendly_name": "Sala"}},
            {"entity_id": "light.kitchen", "state": "off", "attributes": {"friendly_name": "Kitchen"}},
        ]
        app, ha, discovery = _make_app(entities=entities)
        await mod.setup(app)
        ctx = _make_context()
        await mod.handle_command("devices", ["light"], ctx)
        ctx.update.message.reply_text.assert_awaited_once()
        text = ctx.update.message.reply_text.call_args[0][0]
        assert "light" in text

    async def test_cmd_devices_no_entities_sends_not_found(self):
        mod = DevicesModule()
        app, ha, discovery = _make_app(entities=[])
        await mod.setup(app)
        ctx = _make_context()
        await mod.handle_command("devices", ["light"], ctx)
        ctx.update.message.reply_text.assert_awaited_once()

    async def test_cmd_status_sends_entity_state(self):
        mod = DevicesModule()
        app, ha, _ = _make_app()
        await mod.setup(app)
        ctx = _make_context()
        await mod.handle_command("status", ["light.sala"], ctx)
        ha.get_state.assert_awaited_once_with("light.sala")
        ctx.update.message.reply_text.assert_awaited_once()

    async def test_cmd_status_no_args_sends_usage(self):
        mod = DevicesModule()
        app, ha, _ = _make_app()
        await mod.setup(app)
        ctx = _make_context()
        await mod.handle_command("status", [], ctx)
        ha.get_state.assert_not_awaited()
        ctx.update.message.reply_text.assert_awaited_once()

    async def test_cmd_toggle_turns_on_when_off(self):
        mod = DevicesModule()
        app, ha, _ = _make_app()
        ha.get_state = AsyncMock(return_value={"state": "off", "attributes": {"friendly_name": "Sala"}})
        await mod.setup(app)
        ctx = _make_context()
        await mod.handle_command("toggle", ["light.sala"], ctx)
        ha.call_service.assert_awaited_once()
        call_args = ha.call_service.call_args[0]
        assert call_args[1] == "turn_on"

    async def test_cmd_toggle_turns_off_when_on(self):
        mod = DevicesModule()
        app, ha, _ = _make_app()
        ha.get_state = AsyncMock(return_value={"state": "on", "attributes": {"friendly_name": "Sala"}})
        await mod.setup(app)
        ctx = _make_context()
        await mod.handle_command("toggle", ["light.sala"], ctx)
        ha.call_service.assert_awaited_once()
        call_args = ha.call_service.call_args[0]
        assert call_args[1] == "turn_off"

    async def test_cmd_toggle_no_args_sends_usage(self):
        mod = DevicesModule()
        app, ha, _ = _make_app()
        await mod.setup(app)
        ctx = _make_context()
        await mod.handle_command("toggle", [], ctx)
        ha.call_service.assert_not_awaited()
        ctx.update.message.reply_text.assert_awaited_once()

    async def test_no_discovery_sends_error(self):
        mod = DevicesModule()
        app, ha, _ = _make_app()
        app.extra = {}  # remove discovery
        await mod.setup(app)
        ctx = _make_context()
        await mod.handle_command("devices", ["light"], ctx)
        ctx.update.message.reply_text.assert_awaited_once()
