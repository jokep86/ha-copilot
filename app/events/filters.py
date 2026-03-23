"""
Event filter: domain, entity pattern, and cooldown checks.
Returns True when an event should be forwarded as a notification.
"""
from __future__ import annotations

import re
import time
from typing import TYPE_CHECKING

from app.observability.logger import get_logger

if TYPE_CHECKING:
    from app.config import AppConfig

logger = get_logger(__name__)


class EventFilter:
    def __init__(self, config: "AppConfig") -> None:
        self._config = config
        # entity_id → monotonic timestamp of last notification sent
        self._last_sent: dict[str, float] = {}

    def should_notify(self, event: dict) -> bool:
        """
        Return True if this event passes all filters and should be sent.
        Checks: proactive_notifications flag, domain, entity pattern, cooldown.
        """
        if not self._config.proactive_notifications:
            return False

        data = event.get("data", {})
        entity_id: str = data.get("entity_id", "")
        if not entity_id:
            return False

        domain = entity_id.split(".")[0]

        # Domain filter (if configured, entity must match one of the domains)
        allowed_domains = self._config.notification_domains
        if allowed_domains and domain not in allowed_domains:
            return False

        # Entity pattern filter (if configured, entity_id must match at least one)
        patterns = self._config.notification_entity_patterns
        if patterns:
            if not any(re.search(p, entity_id) for p in patterns if p):
                return False

        # Cooldown — use 60s default; no per-subscription granularity at this level
        now = time.monotonic()
        last = self._last_sent.get(entity_id, 0.0)
        # Pick the smallest cooldown from configured conditions (or 60s default)
        cooldown = 60
        if now - last < cooldown:
            return False

        self._last_sent[entity_id] = now
        return True

    def reset_cooldown(self, entity_id: str) -> None:
        self._last_sent.pop(entity_id, None)
