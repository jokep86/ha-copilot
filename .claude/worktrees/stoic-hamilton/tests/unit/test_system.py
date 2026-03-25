"""
Unit tests for SystemModule.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
import pytest

from app.modules.system import SystemModule


def _make_app(ha_config=None, sup_info=None, host_info=None, os_info=None, domains=None):
    ha = MagicMock()
    ha.get_config = AsyncMock(return_value=ha_config or {
        "version": "2026.3.4", "location_name": "Home"
    })

    sup = MagicMock()
    sup.get_info = AsyncMock(return_value=sup_info or {"version": "2026.03.0"})
    sup.get_host_info = AsyncMock(return_value=host_info or {
        "hostname": "homeassistant", "chassis": "vm"
    })
    sup.get_os_info = AsyncMock(return_value=os_info or {
        "version": "12.0", "board": "generic-x86-64"
    })

    discovery = MagicMock()
    discovery.get_domains = AsyncMock(return_value=domains or {"light": 5, "switch": 3})

    from app.core.degradation import DegradationMap
    deg = DegradationMap()

    app = MagicMock()
    app.ha_client = ha
    app.supervisor_client = sup
    app.extra = {"discovery": discovery, "degradation": deg}
    return app, ha, sup, discovery, deg


def _ctx():
    ctx = MagicMock()
    ctx.user_id = 1
    ctx.update = MagicMock()
    ctx.update.message = MagicMock()
    ctx.update.message.reply_text = AsyncMock()
    return ctx


class TestSystemModule:
    async def test_sys_sends_message(self):
        mod = SystemModule()
        app, *_ = _make_app()
        await mod.setup(app)
        ctx = _ctx()
        await mod.handle_command("sys", [], ctx)
        ctx.update.message.reply_text.assert_awaited_once()

    async def test_sys_includes_ha_version(self):
        mod = SystemModule()
        app, *_ = _make_app()
        await mod.setup(app)
        ctx = _ctx()
        await mod.handle_command("sys", [], ctx)
        text = ctx.update.message.reply_text.call_args[0][0]
        # MarkdownV2 escapes dots: 2026.3.4 → 2026\.3\.4
        assert "2026" in text and "3" in text and "4" in text

    async def test_sys_includes_component_health(self):
        mod = SystemModule()
        app, ha, sup, discovery, deg = _make_app()
        deg.set_degraded("websocket", "connection lost")
        await mod.setup(app)
        ctx = _ctx()
        await mod.handle_command("sys", [], ctx)
        text = ctx.update.message.reply_text.call_args[0][0]
        # Should show some health emoji
        assert "🟢" in text or "🟡" in text or "🔴" in text

    async def test_sys_ha_unavailable_continues(self):
        mod = SystemModule()
        app, ha, sup, *_ = _make_app()
        ha.get_config = AsyncMock(side_effect=Exception("HA unreachable"))
        await mod.setup(app)
        ctx = _ctx()
        # Should not raise — degraded behavior
        await mod.handle_command("sys", [], ctx)
        ctx.update.message.reply_text.assert_awaited_once()

    async def test_sys_supervisor_unavailable_continues(self):
        mod = SystemModule()
        app, ha, sup, *_ = _make_app()
        sup.get_info = AsyncMock(side_effect=Exception("Supervisor unreachable"))
        await mod.setup(app)
        ctx = _ctx()
        await mod.handle_command("sys", [], ctx)
        ctx.update.message.reply_text.assert_awaited_once()

    async def test_sys_includes_entity_count(self):
        mod = SystemModule()
        app, *_ = _make_app(domains={"light": 10, "switch": 5})
        await mod.setup(app)
        ctx = _ctx()
        await mod.handle_command("sys", [], ctx)
        text = ctx.update.message.reply_text.call_args[0][0]
        assert "15" in text
