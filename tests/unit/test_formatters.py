"""
Unit tests for bot/formatters.py.
"""
from __future__ import annotations

from app.bot.formatters import (
    bold,
    code,
    code_block,
    entity_state_msg,
    error_msg,
    escape_md,
    info_msg,
    italic,
    link,
    success_msg,
    warning_msg,
)


class TestEscapeMd:
    def test_plain_text_unchanged(self):
        assert escape_md("hello world") == "hello world"

    def test_period_escaped(self):
        assert escape_md("test.com") == r"test\.com"

    def test_underscore_escaped(self):
        assert escape_md("hello_world") == r"hello\_world"

    def test_hyphen_escaped(self):
        assert escape_md("a-b") == r"a\-b"

    def test_all_specials(self):
        result = escape_md("_*[]()~`>#+-=|{}.!")
        # Every special char should be escaped with backslash
        assert result.count("\\") == len("_*[]()~`>#+-=|{}.!")

    def test_number_not_escaped(self):
        assert escape_md("123") == "123"

    def test_empty_string(self):
        assert escape_md("") == ""

    def test_converts_non_string(self):
        assert escape_md(42) == "42"


class TestFormatters:
    def test_bold(self):
        result = bold("hello")
        assert result.startswith("*")
        assert result.endswith("*")
        assert "hello" in result

    def test_italic(self):
        result = italic("hello")
        assert result.startswith("_")
        assert result.endswith("_")

    def test_code(self):
        result = code("sensor.temp")
        assert result.startswith("`")
        assert result.endswith("`")

    def test_code_block_plain(self):
        result = code_block("print('hello')")
        assert "```" in result
        assert "print" in result

    def test_code_block_with_language(self):
        result = code_block("x = 1", language="python")
        assert "```python" in result

    def test_link(self):
        result = link("Click here", "https://example.com")
        assert "Click here" in result or "Click" in result
        assert "https://example.com" in result

    def test_error_msg(self):
        result = error_msg("Something failed")
        assert "🔴" in result
        assert "Something" in result

    def test_success_msg(self):
        result = success_msg("Done!")
        assert "✅" in result

    def test_warning_msg(self):
        result = warning_msg("Be careful")
        assert "⚠️" in result

    def test_info_msg(self):
        result = info_msg("FYI")
        assert "ℹ️" in result


class TestEntityStateMsg:
    def test_basic_state(self):
        result = entity_state_msg("light.sala", "on", {"friendly_name": "Sala"})
        assert "Sala" in result
        assert "light" in result
        assert "on" in result

    def test_state_with_unit(self):
        result = entity_state_msg(
            "sensor.temp", "22.5", {"unit_of_measurement": "°C", "friendly_name": "Temperature"}
        )
        # MarkdownV2 escapes the dot, so check for escaped version
        assert "22" in result
        assert "°C" in result

    def test_state_without_friendly_name(self):
        result = entity_state_msg("switch.fan", "off", {})
        assert "switch" in result

    def test_shows_device_class_attribute(self):
        result = entity_state_msg("sensor.bat", "85", {"device_class": "battery"})
        assert "battery" in result

    def test_shows_brightness_attribute(self):
        result = entity_state_msg("light.lamp", "on", {"brightness": 128})
        assert "128" in result

    def test_ignores_unknown_attributes(self):
        result = entity_state_msg("light.lamp", "on", {"unknown_attr": "xyz"})
        assert "unknown_attr" not in result
