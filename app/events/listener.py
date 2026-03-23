"""
WebSocket event subscription manager.
Subscribes to configured HA event types, applies filters, sends notifications.
Supports per-user enable/disable.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from app.bot.formatters import escape_md
from app.events.filters import EventFilter
from app.observability.logger import get_logger

if TYPE_CHECKING:
    from app.config import AppConfig
    from app.events.notifier import Notifier
    from app.ha.websocket import HAWebSocket

logger = get_logger(__name__)

# State changes that are interesting enough to notify
_INTERESTING_STATES = {
    "on", "off", "home", "away", "open", "closed",
    "locked", "unlocked", "triggered", "armed_home",
    "armed_away", "armed_night", "disarmed", "detected",
    "clear", "problem", "unavailable",
}


class EventListener:
    def __init__(self, config: "AppConfig", notifier: "Notifier") -> None:
        self._config = config
        self._notifier = notifier
        self._filter = EventFilter(config)
        # Users that have notifications enabled (default: all allowed)
        self._enabled: set[int] = set(config.allowed_telegram_ids)
        self._subscribed_types: list[str] = []

    async def start(self, ws: "HAWebSocket") -> None:
        """Subscribe to all configured event types."""
        for event_type in self._config.notification_events:
            await ws.subscribe_events(event_type, self._handle_event)
            self._subscribed_types.append(event_type)
            logger.info("event_listener_subscribed", event_type=event_type)

    def enable(self, user_id: int) -> None:
        self._enabled.add(user_id)
        logger.info("notifications_enabled", user_id=user_id)

    def disable(self, user_id: int) -> None:
        self._enabled.discard(user_id)
        logger.info("notifications_disabled", user_id=user_id)

    def is_enabled(self, user_id: int) -> bool:
        return user_id in self._enabled

    def get_subscribed_types(self) -> list[str]:
        return list(self._subscribed_types)

    # ------------------------------------------------------------------ #

    async def _handle_event(self, event: dict) -> None:
        """Called by HAWebSocket for every subscribed event."""
        if not self._enabled:
            return

        if not self._filter.should_notify(event):
            return

        message = self._format_event(event)
        if not message:
            return

        event_type = event.get("event_type", "event")
        data = event.get("data", {})
        entity_id = data.get("entity_id")

        logger.debug(
            "event_notification_sending",
            event_type=event_type,
            entity_id=entity_id,
        )
        await self._notifier.send(
            event_type=event_type,
            entity_id=entity_id,
            message=message,
        )

    def _format_event(self, event: dict) -> str | None:
        """Format a HA event as a Telegram notification string."""
        event_type = event.get("event_type", "")
        data = event.get("data", {})

        if event_type == "state_changed":
            entity_id: str = data.get("entity_id", "")
            new_state = data.get("new_state") or {}
            old_state = data.get("old_state") or {}

            new = new_state.get("state", "?")
            old = old_state.get("state", "?")

            # Only notify on meaningful state transitions
            if new == old:
                return None
            if new not in _INTERESTING_STATES and old not in _INTERESTING_STATES:
                return None

            fname = new_state.get("attributes", {}).get("friendly_name", entity_id)
            icon = _state_icon(new)
            return f"{icon} {escape_md(fname)}: {escape_md(old)} → {escape_md(new)}"

        if event_type == "automation_triggered":
            auto_id = data.get("entity_id", data.get("name", "?"))
            return f"⚡ Automation triggered: {escape_md(str(auto_id))}"

        # Generic fallback
        return f"🔔 {escape_md(event_type)}"


def _state_icon(state: str) -> str:
    return {
        "on": "🟢", "home": "🏠", "open": "🚪", "unlocked": "🔓",
        "triggered": "🚨", "armed_home": "🔒", "armed_away": "🔒",
        "armed_night": "🔒", "detected": "🚨", "problem": "⚠️",
        "off": "⚫", "away": "🚶", "closed": "✅", "locked": "🔒",
        "disarmed": "✅", "clear": "✅", "unavailable": "🔴",
    }.get(state, "🔔")
