"""
Unit tests for SupervisorManagerModule.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
import pytest

from app.modules.supervisor_mgr import SupervisorManagerModule


def _make_app(addons=None, backups=None):
    sup = MagicMock()
    sup.get_addons = AsyncMock(return_value=addons or [])
    sup.get_backups = AsyncMock(return_value=backups or [])
    sup.get_addon_info = AsyncMock(return_value={
        "name": "Zigbee2MQTT", "state": "started",
        "version": "1.32.0", "description": "Zigbee bridge"
    })
    sup.restart_addon = AsyncMock()
    sup.restart_core = AsyncMock()
    sup.reboot_host = AsyncMock()
    sup.create_backup = AsyncMock(return_value={"slug": "abc123"})

    app = MagicMock()
    app.supervisor_client = sup
    app.extra = {}
    return app, sup


def _ctx():
    ctx = MagicMock()
    ctx.user_id = 1
    ctx.update = MagicMock()
    ctx.update.message = MagicMock()
    ctx.update.message.reply_text = AsyncMock()
    return ctx


class TestSupervisorManagerModule:
    async def test_addons_empty(self):
        mod = SupervisorManagerModule()
        app, sup = _make_app()
        await mod.setup(app)
        await mod.handle_command("addons", [], _ctx())
        sup.get_addons.assert_awaited_once()

    async def test_addons_lists_with_update_flag(self):
        mod = SupervisorManagerModule()
        app, sup = _make_app(addons=[
            {"name": "MQTT", "slug": "core_mosquitto", "state": "started",
             "version": "6.2.1", "update_available": True},
        ])
        await mod.setup(app)
        ctx = _ctx()
        await mod.handle_command("addons", [], ctx)
        text = ctx.update.message.reply_text.call_args[0][0]
        assert "⬆️" in text

    async def test_addon_info(self):
        mod = SupervisorManagerModule()
        app, sup = _make_app()
        await mod.setup(app)
        ctx = _ctx()
        await mod.handle_command("addon", ["core_mosquitto", "info"], ctx)
        sup.get_addon_info.assert_awaited_once_with("core_mosquitto")

    async def test_addon_restart_requires_confirm(self):
        mod = SupervisorManagerModule()
        app, sup = _make_app()
        await mod.setup(app)
        ctx = _ctx()
        await mod.handle_command("addon", ["core_mosquitto", "restart"], ctx)
        sup.restart_addon.assert_not_awaited()
        text = ctx.update.message.reply_text.call_args[0][0]
        assert "confirm" in text

    async def test_addon_restart_with_confirm(self):
        mod = SupervisorManagerModule()
        app, sup = _make_app()
        await mod.setup(app)
        await mod.handle_command("addon", ["core_mosquitto", "restart", "confirm"], _ctx())
        sup.restart_addon.assert_awaited_once_with("core_mosquitto")

    async def test_backup_list(self):
        mod = SupervisorManagerModule()
        app, sup = _make_app(backups=[
            {"name": "Full Backup", "slug": "abc", "date": "2026-03-01T00:00:00Z",
             "size": 104857600, "type": "full"},
        ])
        await mod.setup(app)
        ctx = _ctx()
        await mod.handle_command("backup", ["list"], ctx)
        text = ctx.update.message.reply_text.call_args[0][0]
        assert "Full Backup" in text or "100" in text

    async def test_backup_create(self):
        mod = SupervisorManagerModule()
        app, sup = _make_app()
        await mod.setup(app)
        await mod.handle_command("backup", ["create"], _ctx())
        sup.create_backup.assert_awaited_once()

    async def test_restart_requires_confirm(self):
        mod = SupervisorManagerModule()
        app, sup = _make_app()
        await mod.setup(app)
        ctx = _ctx()
        await mod.handle_command("restart", ["core"], ctx)
        sup.restart_core.assert_not_awaited()
        text = ctx.update.message.reply_text.call_args[0][0]
        assert "confirm" in text

    async def test_restart_core_with_confirm(self):
        mod = SupervisorManagerModule()
        app, sup = _make_app()
        await mod.setup(app)
        await mod.handle_command("restart", ["core", "confirm"], _ctx())
        sup.restart_core.assert_awaited_once()

    async def test_reboot_requires_confirm(self):
        mod = SupervisorManagerModule()
        app, sup = _make_app()
        await mod.setup(app)
        ctx = _ctx()
        await mod.handle_command("reboot", [], ctx)
        sup.reboot_host.assert_not_awaited()
        text = ctx.update.message.reply_text.call_args[0][0]
        assert "confirm" in text

    async def test_reboot_with_confirm(self):
        mod = SupervisorManagerModule()
        app, sup = _make_app()
        await mod.setup(app)
        await mod.handle_command("reboot", ["confirm"], _ctx())
        sup.reboot_host.assert_awaited_once()
