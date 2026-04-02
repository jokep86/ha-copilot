"""
Unit tests for observability logger setup.
"""
from __future__ import annotations

import logging
from pathlib import Path
from unittest.mock import patch, MagicMock
import pytest


class TestSetupLogging:
    def test_get_logger_returns_bound_logger(self):
        from app.observability.logger import get_logger
        logger = get_logger("test.module")
        assert logger is not None

    def test_setup_logging_info_level(self, tmp_path):
        from app.observability.logger import setup_logging
        with patch("app.observability.logger.LOGS_DIR", tmp_path):
            setup_logging("info")
        assert (tmp_path / "ha_copilot.log").exists()

    def test_setup_logging_debug_level(self, tmp_path):
        from app.observability.logger import setup_logging
        with patch("app.observability.logger.LOGS_DIR", tmp_path):
            setup_logging("debug")
        assert (tmp_path / "ha_copilot.log").exists()

    def test_setup_logging_warning_level(self, tmp_path):
        from app.observability.logger import setup_logging
        with patch("app.observability.logger.LOGS_DIR", tmp_path):
            setup_logging("warning")
        assert (tmp_path / "ha_copilot.log").exists()

    def test_setup_logging_invalid_level_defaults_to_info(self, tmp_path):
        from app.observability.logger import setup_logging
        with patch("app.observability.logger.LOGS_DIR", tmp_path):
            setup_logging("nonexistent")  # should not raise, fallback to INFO
        assert (tmp_path / "ha_copilot.log").exists()

    def test_setup_logging_creates_dir(self, tmp_path):
        from app.observability.logger import setup_logging
        nested = tmp_path / "nested" / "logs"
        with patch("app.observability.logger.LOGS_DIR", nested):
            setup_logging("info")
        assert nested.exists()
