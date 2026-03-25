"""
Telegram message formatting.
Uses MarkdownV2 (required by python-telegram-bot for rich text).
"""
from __future__ import annotations

import re
from typing import Any

# Characters that must be escaped in MarkdownV2
_MD2_SPECIAL = r"\_*[]()~`>#+-=|{}.!"


def escape_md(text: str) -> str:
    """Escape all MarkdownV2 special characters."""
    return re.sub(f"([{re.escape(_MD2_SPECIAL)}])", r"\\\1", str(text))


def bold(text: str) -> str:
    return f"*{escape_md(text)}*"


def italic(text: str) -> str:
    return f"_{escape_md(text)}_"


def code(text: str) -> str:
    return f"`{escape_md(text)}`"


def code_block(text: str, language: str = "") -> str:
    # Backticks inside code blocks must be escaped differently
    escaped = text.replace("\\", "\\\\").replace("`", "\\`")
    return f"```{language}\n{escaped}\n```"


def link(text: str, url: str) -> str:
    return f"[{escape_md(text)}]({url})"


# --- Semantic helpers ---

def error_msg(text: str) -> str:
    return f"🔴 {escape_md(text)}"


def success_msg(text: str) -> str:
    return f"✅ {escape_md(text)}"


def warning_msg(text: str) -> str:
    return f"⚠️ {escape_md(text)}"


def info_msg(text: str) -> str:
    return f"ℹ️ {escape_md(text)}"


def entity_state_msg(entity_id: str, state: str, attributes: dict[str, Any]) -> str:
    """Format a single entity state for display."""
    friendly = attributes.get("friendly_name", entity_id)
    unit = attributes.get("unit_of_measurement", "")
    state_str = f"{state} {unit}".strip()

    lines = [
        bold(friendly),
        f"ID: {code(entity_id)}",
        f"State: {code(state_str)}",
    ]

    show_attrs = ["device_class", "battery_level", "brightness", "color_temp"]
    for attr in show_attrs:
        if attr in attributes:
            lines.append(f"{escape_md(attr)}: {code(str(attributes[attr]))}")

    return "\n".join(lines)
