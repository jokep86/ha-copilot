"""
Inline keyboard pagination for long entity/automation lists.
"""
from __future__ import annotations

import math
from typing import Any, TypeVar

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

T = TypeVar("T")

PAGE_SIZE = 10
CALLBACK_PREFIX = "page"


def paginate(
    items: list[T],
    page: int = 0,
    page_size: int = PAGE_SIZE,
) -> tuple[list[T], InlineKeyboardMarkup | None]:
    """
    Slice items for the given page and build a navigation keyboard.
    Returns (page_items, keyboard) — keyboard is None when only one page.
    """
    total = len(items)
    if total == 0:
        return [], None

    total_pages = max(1, math.ceil(total / page_size))
    page = max(0, min(page, total_pages - 1))

    start = page * page_size
    page_items = items[start : start + page_size]

    if total_pages <= 1:
        return page_items, None

    buttons: list[InlineKeyboardButton] = []
    if page > 0:
        buttons.append(
            InlineKeyboardButton("⬅️ Prev", callback_data=f"{CALLBACK_PREFIX}:{page - 1}")
        )
    buttons.append(
        InlineKeyboardButton(f"{page + 1}/{total_pages}", callback_data="noop")
    )
    if page < total_pages - 1:
        buttons.append(
            InlineKeyboardButton("Next ➡️", callback_data=f"{CALLBACK_PREFIX}:{page + 1}")
        )

    return page_items, InlineKeyboardMarkup([buttons])


def parse_page_callback(data: str) -> int | None:
    """Parse a page callback. Returns page number or None if not a page callback."""
    if data.startswith(f"{CALLBACK_PREFIX}:"):
        try:
            return int(data.split(":", 1)[1])
        except (ValueError, IndexError):
            return None
    return None
