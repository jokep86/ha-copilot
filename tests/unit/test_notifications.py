"""
Unit tests for NotificationsModule.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
import pytest

from app.modules.notifications import NotificationsModule


def _make_listener(enabled=True, types=None):
    listener = MagicMock()
    listener.is_enabled = MagicMock(return_value=enabled)
    listener.enable = MagicMock()
    listener.disable = MagicMock()
    if types is None:
        types = ["state_changed"]
    listener.get_subscribed_types = MagicMock(return_value=types)
    return listener


def _make_app(listener=None):
    app = MagicMock()
    app.extra = {}
    if listener is not None:
        app.extra["event_listener"] = listener
    return app


def _make_context(user_id=12345):
    ctx = MagicMock()
    ctx.update = MagicMock()
    ctx.update.message = MagicMock()
    ctx.update.message.reply_text = AsyncMock()
    ctx.user_id = user_id
    return ctx


class TestNotificationsModule:
    async def test_setup_stores_app(self):
        mod = NotificationsModule()
        app = _make_app()
        await mod.setup(app)
        assert mod._app is app

    async def test_teardown_is_noop(self):
        mod = NotificationsModule()
        app = _make_app()
        await mod.setup(app)
        await mod.teardown()

    async def test_module_attributes(self):
        mod = NotificationsModule()
        assert "notify" in mod.commands
        assert "subs" in mod.commands
        assert mod.name == "notifications"

    async def test_cmd_notify_no_listener(self):
        mod = NotificationsModule()
        app = _make_app(listener=None)
        await mod.setup(app)
        ctx = _make_context()
        await mod.handle_command("notify", ["on"], ctx)
        text = ctx.update.message.reply_text.call_args[0][0]
        assert "not available" in text or "listener" in text.lower()

    async def test_cmd_notify_on_enables(self):
        listener = _make_listener(enabled=False)
        mod = NotificationsModule()
        app = _make_app(listener=listener)
        await mod.setup(app)
        ctx = _make_context()
        await mod.handle_command("notify", ["on"], ctx)
        listener.enable.assert_called_once_with(ctx.user_id)
        text = ctx.update.message.reply_text.call_args[0][0]
        assert "enabled" in text

    async def test_cmd_notify_off_disables(self):
        listener = _make_listener(enabled=True)
        mod = NotificationsModule()
        app = _make_app(listener=listener)
        await mod.setup(app)
        ctx = _make_context()
        await mod.handle_command("notify", ["off"], ctx)
        listener.disable.assert_called_once_with(ctx.user_id)
        text = ctx.update.message.reply_text.call_args[0][0]
        assert "disabled" in text

    async def test_cmd_notify_invalid_arg(self):
        listener = _make_listener()
        mod = NotificationsModule()
        app = _make_app(listener=listener)
        await mod.setup(app)
        ctx = _make_context()
        await mod.handle_command("notify", ["maybe"], ctx)
        text = ctx.update.message.reply_text.call_args[0][0]
        assert "Usage" in text or "on" in text

    async def test_cmd_notify_no_args_shows_status_enabled(self):
        listener = _make_listener(enabled=True)
        mod = NotificationsModule()
        app = _make_app(listener=listener)
        await mod.setup(app)
        ctx = _make_context()
        await mod.handle_command("notify", [], ctx)
        text = ctx.update.message.reply_text.call_args[0][0]
        assert "on" in text

    async def test_cmd_notify_no_args_shows_status_disabled(self):
        listener = _make_listener(enabled=False)
        mod = NotificationsModule()
        app = _make_app(listener=listener)
        await mod.setup(app)
        ctx = _make_context()
        await mod.handle_command("notify", [], ctx)
        text = ctx.update.message.reply_text.call_args[0][0]
        assert "off" in text

    async def test_cmd_subs_no_listener(self):
        mod = NotificationsModule()
        app = _make_app(listener=None)
        await mod.setup(app)
        ctx = _make_context()
        await mod.handle_command("subs", [], ctx)
        text = ctx.update.message.reply_text.call_args[0][0]
        assert "not available" in text or "listener" in text.lower()

    async def test_cmd_subs_no_subscriptions(self):
        listener = _make_listener(types=[])
        mod = NotificationsModule()
        app = _make_app(listener=listener)
        await mod.setup(app)
        ctx = _make_context()
        await mod.handle_command("subs", [], ctx)
        text = ctx.update.message.reply_text.call_args[0][0]
        assert "No active" in text

    async def test_cmd_subs_shows_types(self):
        listener = _make_listener(types=["state_changed", "automation_triggered"])
        mod = NotificationsModule()
        app = _make_app(listener=listener)
        await mod.setup(app)
        ctx = _make_context()
        await mod.handle_command("subs", [], ctx)
        text = ctx.update.message.reply_text.call_args[0][0]
        # MarkdownV2 escapes underscores as \_
        assert "state" in text and "changed" in text
        assert "automation" in text and "triggered" in text

    async def test_cmd_subs_shows_notification_status(self):
        listener = _make_listener(enabled=True, types=["state_changed"])
        mod = NotificationsModule()
        app = _make_app(listener=listener)
        await mod.setup(app)
        ctx = _make_context()
        await mod.handle_command("subs", [], ctx)
        text = ctx.update.message.reply_text.call_args[0][0]
        # Status string should appear
        assert "enabled" in text or "disabled" in text
