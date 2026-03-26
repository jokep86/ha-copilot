"""
Unit tests for the onboarding wizard in BotHandler._handle_start.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
import pytest

from app.bot.handler import BotHandler, VERSION


def _make_bot(db=None):
    """Build a minimal BotHandler with mocked dependencies."""
    bot = BotHandler(
        config=MagicMock(),
        module_registry=MagicMock(),
        command_queue=MagicMock(),
        auth=MagicMock(),
        degradation=MagicMock(),
        dead_man_switch=MagicMock(),
        db=db,
    )
    # auth always passes
    bot.auth.check = AsyncMock(return_value=True)
    return bot


def _make_update():
    update = MagicMock()
    update.effective_user.id = 12345
    update.effective_chat.id = 12345
    update.message.reply_text = AsyncMock()
    return update


class TestOnboardingWizard:
    async def test_first_run_shows_wizard(self):
        db = MagicMock()
        db.get_setting = AsyncMock(return_value=None)  # not yet onboarded
        db.set_setting = AsyncMock()
        bot = _make_bot(db=db)
        update = _make_update()
        await bot._handle_start(update, MagicMock())
        text = update.message.reply_text.call_args[0][0]
        assert "Welcome to HA Copilot" in text
        assert "Getting started" in text or "What you can do" in text
        db.set_setting.assert_awaited_once_with("onboarded", "1")

    async def test_second_run_shows_short_welcome(self):
        db = MagicMock()
        db.get_setting = AsyncMock(return_value="1")  # already onboarded
        db.set_setting = AsyncMock()
        bot = _make_bot(db=db)
        update = _make_update()
        await bot._handle_start(update, MagicMock())
        text = update.message.reply_text.call_args[0][0]
        assert "Welcome back" in text
        db.set_setting.assert_not_awaited()

    async def test_no_db_shows_short_welcome(self):
        """When db is None (degraded), show the short welcome."""
        bot = _make_bot(db=None)
        update = _make_update()
        await bot._handle_start(update, MagicMock())
        text = update.message.reply_text.call_args[0][0]
        assert "Welcome back" in text

    async def test_wizard_contains_version(self):
        db = MagicMock()
        db.get_setting = AsyncMock(return_value=None)
        db.set_setting = AsyncMock()
        bot = _make_bot(db=db)
        update = _make_update()
        await bot._handle_start(update, MagicMock())
        text = update.message.reply_text.call_args[0][0]
        # VERSION is MarkdownV2-escaped in the output (e.g. "0\.1\.0")
        escaped_version = VERSION.replace(".", "\\.")
        assert escaped_version in text

    async def test_unauthorized_user_blocked(self):
        db = MagicMock()
        db.get_setting = AsyncMock(return_value=None)
        db.set_setting = AsyncMock()
        bot = _make_bot(db=db)
        bot.auth.check = AsyncMock(return_value=False)
        update = _make_update()
        await bot._handle_start(update, MagicMock())
        update.message.reply_text.assert_not_awaited()
        db.set_setting.assert_not_awaited()
