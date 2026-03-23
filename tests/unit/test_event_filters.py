"""
Unit tests for EventFilter.
"""
from __future__ import annotations

import time
from unittest.mock import MagicMock
import pytest

from app.events.filters import EventFilter


def _config(domains=None, patterns=None, proactive=True):
    cfg = MagicMock()
    cfg.proactive_notifications = proactive
    cfg.notification_domains = domains or []
    cfg.notification_entity_patterns = patterns or []
    return cfg


def _event(entity_id="binary_sensor.door", new_state="on", old_state="off"):
    return {
        "event_type": "state_changed",
        "data": {
            "entity_id": entity_id,
            "new_state": {"state": new_state, "attributes": {}},
            "old_state": {"state": old_state, "attributes": {}},
        }
    }


class TestEventFilter:
    def test_passes_when_no_filters(self):
        f = EventFilter(_config())
        assert f.should_notify(_event()) is True

    def test_blocked_when_proactive_disabled(self):
        f = EventFilter(_config(proactive=False))
        assert f.should_notify(_event()) is False

    def test_domain_filter_blocks_unmatched(self):
        f = EventFilter(_config(domains=["light"]))
        assert f.should_notify(_event("binary_sensor.door")) is False

    def test_domain_filter_allows_matched(self):
        f = EventFilter(_config(domains=["binary_sensor"]))
        assert f.should_notify(_event("binary_sensor.door")) is True

    def test_entity_pattern_blocks_unmatched(self):
        f = EventFilter(_config(patterns=["^light\\..*"]))
        assert f.should_notify(_event("binary_sensor.door")) is False

    def test_entity_pattern_allows_matched(self):
        f = EventFilter(_config(patterns=[".*door.*"]))
        assert f.should_notify(_event("binary_sensor.door")) is True

    def test_cooldown_blocks_second_event(self):
        f = EventFilter(_config())
        assert f.should_notify(_event()) is True
        # Second event for same entity within cooldown → blocked
        assert f.should_notify(_event()) is False

    def test_cooldown_resets_after_reset_call(self):
        f = EventFilter(_config())
        f.should_notify(_event("light.sala"))
        f.reset_cooldown("light.sala")
        assert f.should_notify(_event("light.sala")) is True

    def test_no_entity_id_blocked(self):
        f = EventFilter(_config())
        event = {"event_type": "state_changed", "data": {}}
        assert f.should_notify(event) is False

    def test_different_entities_independent_cooldown(self):
        f = EventFilter(_config())
        assert f.should_notify(_event("light.sala")) is True
        assert f.should_notify(_event("light.kitchen")) is True
