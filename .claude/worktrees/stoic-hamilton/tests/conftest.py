"""
Shared pytest fixtures for ha-copilot tests.
"""
from __future__ import annotations

import asyncio
import os
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio

# Point config and DB at test fixtures
os.environ.setdefault("HA_OPTIONS_PATH", str(Path(__file__).parent / "fixtures" / "options.json"))
os.environ.setdefault("HA_DB_PATH", ":memory:")
os.environ.setdefault("HA_LOGS_DIR", str(Path(__file__).parent / "tmp" / "logs"))
os.environ.setdefault("HA_MIGRATIONS_DIR", str(Path(__file__).parent.parent / "migrations"))


from app.config import AppConfig, ConfirmationLevelsConfig


@pytest.fixture
def config() -> AppConfig:
    return AppConfig(
        telegram_bot_token="test_bot_token",
        allowed_telegram_ids=[111111, 222222],
        anthropic_api_key="test_anthropic_key",
        allowed_group_ids=[],
        chat_mode="both",
    )


@pytest.fixture
def config_private(config: AppConfig) -> AppConfig:
    config.chat_mode = "private"
    return config


@pytest.fixture
def config_group(config: AppConfig) -> AppConfig:
    config.chat_mode = "group"
    return config
