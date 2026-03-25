"""
Unit tests for AuthMiddleware.
Tests: allowed/rejected users, chat_mode, group allowlist.
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from telegram import Chat, Update, User

from app.config import AppConfig
from app.middleware.auth import AuthMiddleware


def _make_update(
    user_id: int,
    chat_type: str = "private",
    chat_id: int | None = None,
    username: str = "testuser",
) -> Update:
    user = MagicMock(spec=User)
    user.id = user_id
    user.username = username

    chat = MagicMock(spec=Chat)
    chat.type = chat_type
    chat.id = chat_id if chat_id is not None else user_id

    update = MagicMock(spec=Update)
    update.update_id = 1
    update.effective_user = user
    update.effective_chat = chat
    return update


@pytest.fixture
def auth(config: AppConfig) -> AuthMiddleware:
    return AuthMiddleware(config)


# --- Allowed / rejected ---

def test_allowed_user_private(auth: AuthMiddleware) -> None:
    assert auth.is_authorized(_make_update(111111, "private")) is True


def test_rejected_unknown_user(auth: AuthMiddleware) -> None:
    assert auth.is_authorized(_make_update(999999, "private")) is False


def test_no_effective_user_rejected(auth: AuthMiddleware) -> None:
    update = MagicMock(spec=Update)
    update.update_id = 1
    update.effective_user = None
    assert auth.is_authorized(update) is False


# --- chat_mode: private ---

def test_private_mode_allows_private_chat(config: AppConfig) -> None:
    config.chat_mode = "private"
    auth = AuthMiddleware(config)
    assert auth.is_authorized(_make_update(111111, "private")) is True


def test_private_mode_blocks_group(config: AppConfig) -> None:
    config.chat_mode = "private"
    auth = AuthMiddleware(config)
    assert auth.is_authorized(_make_update(111111, "group")) is False


# --- chat_mode: group ---

def test_group_mode_allows_group(config: AppConfig) -> None:
    config.chat_mode = "group"
    auth = AuthMiddleware(config)
    assert auth.is_authorized(_make_update(111111, "group")) is True


def test_group_mode_blocks_private(config: AppConfig) -> None:
    config.chat_mode = "group"
    auth = AuthMiddleware(config)
    assert auth.is_authorized(_make_update(111111, "private")) is False


# --- chat_mode: both ---

def test_both_mode_allows_private(auth: AuthMiddleware) -> None:
    assert auth.is_authorized(_make_update(111111, "private")) is True


def test_both_mode_allows_group(auth: AuthMiddleware) -> None:
    assert auth.is_authorized(_make_update(111111, "group")) is True


# --- Group allowlist ---

def test_group_allowlist_blocks_unlisted_group(config: AppConfig) -> None:
    config.allowed_group_ids = [777]
    auth = AuthMiddleware(config)
    assert auth.is_authorized(_make_update(111111, "group", chat_id=888)) is False


def test_group_allowlist_allows_listed_group(config: AppConfig) -> None:
    config.allowed_group_ids = [777]
    auth = AuthMiddleware(config)
    assert auth.is_authorized(_make_update(111111, "group", chat_id=777)) is True


def test_group_allowlist_empty_allows_any_group(config: AppConfig) -> None:
    config.allowed_group_ids = []
    auth = AuthMiddleware(config)
    assert auth.is_authorized(_make_update(111111, "group", chat_id=999)) is True


# --- Multiple allowed IDs ---

def test_second_allowed_user_passes(auth: AuthMiddleware) -> None:
    assert auth.is_authorized(_make_update(222222, "private")) is True


# --- Async check ---

@pytest.mark.asyncio
async def test_async_check_authorized(auth: AuthMiddleware) -> None:
    result = await auth.check(_make_update(111111))
    assert result is True


@pytest.mark.asyncio
async def test_async_check_unauthorized(auth: AuthMiddleware) -> None:
    result = await auth.check(_make_update(555555))
    assert result is False
