"""
Unit tests for bot/pagination.py.
Covers: paginate() slicing + keyboard building, parse_page_callback().
"""
from __future__ import annotations

import pytest

from app.bot.pagination import PAGE_SIZE, CALLBACK_PREFIX, paginate, parse_page_callback


# ---------------------------------------------------------------------------
# paginate — empty and single-page cases
# ---------------------------------------------------------------------------

class TestPaginateEmpty:
    def test_empty_list_returns_empty_and_no_keyboard(self):
        items, kb = paginate([])
        assert items == []
        assert kb is None


class TestPaginateSinglePage:
    def test_fewer_than_page_size_returns_all_items(self):
        items = list(range(5))
        result, kb = paginate(items)
        assert result == items
        assert kb is None

    def test_exactly_page_size_returns_all_items(self):
        items = list(range(PAGE_SIZE))
        result, kb = paginate(items)
        assert result == items
        assert kb is None

    def test_single_item(self):
        result, kb = paginate(["only"])
        assert result == ["only"]
        assert kb is None


# ---------------------------------------------------------------------------
# paginate — multi-page slicing
# ---------------------------------------------------------------------------

class TestPaginateSlicing:
    def test_page_zero_returns_first_slice(self):
        items = list(range(25))
        result, _ = paginate(items, page=0)
        assert result == list(range(PAGE_SIZE))

    def test_page_one_returns_second_slice(self):
        items = list(range(25))
        result, _ = paginate(items, page=1)
        assert result == list(range(PAGE_SIZE, 20))

    def test_last_page_returns_remainder(self):
        items = list(range(25))
        result, _ = paginate(items, page=2)
        assert result == [20, 21, 22, 23, 24]

    def test_custom_page_size(self):
        items = list(range(10))
        result, _ = paginate(items, page=0, page_size=3)
        assert result == [0, 1, 2]

    def test_custom_page_size_last_page(self):
        items = list(range(7))
        result, _ = paginate(items, page=2, page_size=3)
        assert result == [6]


# ---------------------------------------------------------------------------
# paginate — page clamping
# ---------------------------------------------------------------------------

class TestPaginateClamping:
    def test_negative_page_clamped_to_zero(self):
        items = list(range(25))
        result, _ = paginate(items, page=-5)
        assert result == list(range(PAGE_SIZE))

    def test_page_beyond_max_clamped_to_last(self):
        items = list(range(25))
        result, _ = paginate(items, page=99)
        assert result == [20, 21, 22, 23, 24]


# ---------------------------------------------------------------------------
# paginate — keyboard structure
# ---------------------------------------------------------------------------

class TestPaginateKeyboard:
    def test_keyboard_exists_when_multi_page(self):
        items = list(range(25))
        _, kb = paginate(items, page=0)
        assert kb is not None

    def test_first_page_has_no_prev_button(self):
        items = list(range(25))
        _, kb = paginate(items, page=0)
        buttons = kb.inline_keyboard[0]
        labels = [b.text for b in buttons]
        assert not any("Prev" in t for t in labels)

    def test_first_page_has_next_button(self):
        items = list(range(25))
        _, kb = paginate(items, page=0)
        buttons = kb.inline_keyboard[0]
        labels = [b.text for b in buttons]
        assert any("Next" in t for t in labels)

    def test_middle_page_has_both_buttons(self):
        items = list(range(35))  # 4 pages with default PAGE_SIZE
        _, kb = paginate(items, page=1)
        buttons = kb.inline_keyboard[0]
        labels = [b.text for b in buttons]
        assert any("Prev" in t for t in labels)
        assert any("Next" in t for t in labels)

    def test_last_page_has_no_next_button(self):
        items = list(range(25))
        _, kb = paginate(items, page=2)
        buttons = kb.inline_keyboard[0]
        labels = [b.text for b in buttons]
        assert not any("Next" in t for t in labels)

    def test_last_page_has_prev_button(self):
        items = list(range(25))
        _, kb = paginate(items, page=2)
        buttons = kb.inline_keyboard[0]
        labels = [b.text for b in buttons]
        assert any("Prev" in t for t in labels)

    def test_page_indicator_button_has_noop_callback(self):
        items = list(range(25))
        _, kb = paginate(items, page=0)
        buttons = kb.inline_keyboard[0]
        noop_buttons = [b for b in buttons if b.callback_data == "noop"]
        assert len(noop_buttons) == 1

    def test_page_indicator_shows_current_and_total(self):
        items = list(range(25))
        _, kb = paginate(items, page=1)
        buttons = kb.inline_keyboard[0]
        indicator = next(b for b in buttons if b.callback_data == "noop")
        assert "2" in indicator.text   # page 1 → displays as "2"
        assert "3" in indicator.text   # total pages for 25 items

    def test_next_button_callback_data(self):
        items = list(range(25))
        _, kb = paginate(items, page=0)
        buttons = kb.inline_keyboard[0]
        next_btn = next(b for b in buttons if "Next" in b.text)
        assert next_btn.callback_data == f"{CALLBACK_PREFIX}:1"

    def test_prev_button_callback_data(self):
        items = list(range(25))
        _, kb = paginate(items, page=2)
        buttons = kb.inline_keyboard[0]
        prev_btn = next(b for b in buttons if "Prev" in b.text)
        assert prev_btn.callback_data == f"{CALLBACK_PREFIX}:1"


# ---------------------------------------------------------------------------
# parse_page_callback
# ---------------------------------------------------------------------------

class TestParsePageCallback:
    def test_returns_page_number_for_valid_callback(self):
        assert parse_page_callback(f"{CALLBACK_PREFIX}:3") == 3

    def test_returns_zero_for_page_zero(self):
        assert parse_page_callback(f"{CALLBACK_PREFIX}:0") == 0

    def test_returns_none_for_wrong_prefix(self):
        assert parse_page_callback("domain:light") is None

    def test_returns_none_for_noop(self):
        assert parse_page_callback("noop") is None

    def test_returns_none_for_non_numeric_page(self):
        assert parse_page_callback(f"{CALLBACK_PREFIX}:abc") is None

    def test_returns_none_for_empty_string(self):
        assert parse_page_callback("") is None
