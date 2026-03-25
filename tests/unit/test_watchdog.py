"""
Unit tests for SelfHealingWatchdog.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch, call
import pytest

from app.alerts.watchdog import SelfHealingWatchdog


def _make_state(entity_id: str, last_updated: str) -> dict:
    return {"entity_id": entity_id, "last_updated": last_updated, "state": "on"}


def _old_ts(hours: int = 3) -> str:
    """Return an ISO timestamp `hours` ago."""
    dt = datetime.now(timezone.utc) - timedelta(hours=hours)
    return dt.isoformat()


def _recent_ts() -> str:
    """Return an ISO timestamp 1 minute ago."""
    dt = datetime.now(timezone.utc) - timedelta(minutes=1)
    return dt.isoformat()


def _make_watchdog(states=None):
    config = MagicMock()
    ha = MagicMock()
    ha.get_states = AsyncMock(return_value=states or [])
    sup = MagicMock()
    db = MagicMock()
    db.conn = MagicMock()
    db.conn.execute = AsyncMock()
    db.conn.commit = AsyncMock()
    notifier = MagicMock()
    notifier.send = AsyncMock()
    return SelfHealingWatchdog(config, ha, sup, db, notifier)


class TestSelfHealingWatchdogLifecycle:
    async def test_start_creates_three_tasks(self):
        w = _make_watchdog()
        await w.start()
        assert len(w._tasks) == 3
        names = {t.get_name() for t in w._tasks}
        assert "watchdog_stale" in names
        assert "watchdog_leak" in names
        assert "watchdog_postmortem" in names
        await w.stop()

    async def test_stop_cancels_all_tasks(self):
        w = _make_watchdog()
        await w.start()
        await w.stop()
        assert len(w._tasks) == 0


class TestStaleIntegrationCheck:
    async def test_no_alert_when_all_fresh(self):
        states = [
            _make_state("sensor.temp", _recent_ts()),
            _make_state("sensor.humid", _recent_ts()),
        ]
        w = _make_watchdog(states)
        await w._check_stale_integrations()
        w._notifier.send.assert_not_called()

    async def test_no_alert_for_single_stale_entity(self):
        # Single stale entity is normal; need ≥2 per domain
        states = [
            _make_state("sensor.temp", _old_ts(hours=3)),
            _make_state("sensor.humid", _recent_ts()),
        ]
        w = _make_watchdog(states)
        await w._check_stale_integrations()
        w._notifier.send.assert_not_called()

    async def test_alert_when_two_stale_in_same_domain(self):
        states = [
            _make_state("sensor.temp", _old_ts(hours=3)),
            _make_state("sensor.humid", _old_ts(hours=3)),
        ]
        w = _make_watchdog(states)
        await w._check_stale_integrations()
        w._notifier.send.assert_called_once()
        call_kwargs = w._notifier.send.call_args[1]
        assert call_kwargs["event_type"] == "stale_integration"

    async def test_incident_logged_for_stale_domain(self):
        states = [
            _make_state("sensor.a", _old_ts(hours=3)),
            _make_state("sensor.b", _old_ts(hours=3)),
        ]
        w = _make_watchdog(states)
        await w._check_stale_integrations()
        w._db.conn.execute.assert_called()
        w._db.conn.commit.assert_called()

    async def test_different_domains_no_cross_alert(self):
        # One stale sensor, one stale climate — should not alert (each < 2)
        states = [
            _make_state("sensor.temp", _old_ts(hours=3)),
            _make_state("climate.living", _old_ts(hours=2)),
        ]
        w = _make_watchdog(states)
        await w._check_stale_integrations()
        w._notifier.send.assert_not_called()

    async def test_get_states_failure_is_handled(self):
        w = _make_watchdog()
        w._ha.get_states = AsyncMock(side_effect=Exception("HA offline"))
        # Should not raise
        await w._check_stale_integrations()
        w._notifier.send.assert_not_called()


class TestEntityLeakCheck:
    async def test_baseline_set_on_first_run(self):
        states = [
            _make_state("sensor.a", _recent_ts()),
            _make_state("sensor.b", _recent_ts()),
        ]
        w = _make_watchdog(states)
        await w._check_entity_leaks()
        assert w._domain_baseline == {"sensor": 2}
        w._notifier.send.assert_not_called()

    async def test_no_alert_within_threshold(self):
        # Grow by 10% — below 20% threshold
        states_initial = [_make_state(f"sensor.{i}", _recent_ts()) for i in range(10)]
        states_grown = [_make_state(f"sensor.{i}", _recent_ts()) for i in range(11)]

        w = _make_watchdog(states_initial)
        await w._check_entity_leaks()  # sets baseline

        w._ha.get_states = AsyncMock(return_value=states_grown)
        await w._check_entity_leaks()
        w._notifier.send.assert_not_called()

    async def test_alert_when_domain_exceeds_threshold(self):
        # Grow by 50% — above 20% threshold
        states_initial = [_make_state(f"sensor.{i}", _recent_ts()) for i in range(10)]
        states_grown = [_make_state(f"sensor.{i}", _recent_ts()) for i in range(15)]

        w = _make_watchdog(states_initial)
        await w._check_entity_leaks()  # sets baseline

        w._ha.get_states = AsyncMock(return_value=states_grown)
        await w._check_entity_leaks()

        w._notifier.send.assert_called_once()
        call_kwargs = w._notifier.send.call_args[1]
        assert call_kwargs["event_type"] == "entity_leak"

    async def test_baseline_updated_after_alert_to_prevent_repeat(self):
        states_initial = [_make_state(f"sensor.{i}", _recent_ts()) for i in range(10)]
        states_grown = [_make_state(f"sensor.{i}", _recent_ts()) for i in range(15)]

        w = _make_watchdog(states_initial)
        await w._check_entity_leaks()

        w._ha.get_states = AsyncMock(return_value=states_grown)
        await w._check_entity_leaks()
        # Baseline should now be updated to 15
        assert w._domain_baseline["sensor"] == 15

    async def test_get_states_failure_is_handled(self):
        w = _make_watchdog()
        w._ha.get_states = AsyncMock(side_effect=Exception("HA offline"))
        await w._check_entity_leaks()
        w._notifier.send.assert_not_called()

    async def test_baseline_resets_after_24h(self):
        import time
        states = [_make_state(f"sensor.{i}", _recent_ts()) for i in range(5)]
        w = _make_watchdog(states)
        await w._check_entity_leaks()  # set baseline

        # Simulate 25 hours passed
        w._baseline_set_at = time.monotonic() - (25 * 3600)
        old_baseline = w._domain_baseline.copy()

        states_new = [_make_state(f"sensor.{i}", _recent_ts()) for i in range(8)]
        w._ha.get_states = AsyncMock(return_value=states_new)
        await w._check_entity_leaks()  # should reset, not alert

        assert w._domain_baseline == {"sensor": 8}
        w._notifier.send.assert_not_called()


class TestPostmortemGeneration:
    def _make_db_with_rows(self, rows):
        db = MagicMock()
        cursor = MagicMock()
        cursor.fetchall = AsyncMock(return_value=rows)
        db.conn.execute = AsyncMock(return_value=cursor)
        db.conn.commit = AsyncMock()
        return db

    async def test_no_postmortems_when_no_rows(self):
        w = _make_watchdog()
        w._db = self._make_db_with_rows([])
        await w._generate_pending_postmortems()
        w._notifier.send.assert_not_called()

    async def test_postmortem_written_for_each_row(self):
        rows = [
            (1, "device_unavailable", "warning", "switch.plug",
             "Device offline", "reload_integration", "reloaded ok", "2026-03-25T10:00:00"),
        ]
        w = _make_watchdog()
        w._db = self._make_db_with_rows(rows)
        await w._generate_pending_postmortems()
        # DB execute called for query + insert
        assert w._db.conn.execute.call_count >= 2
        w._notifier.send.assert_called_once()
        call_kwargs = w._notifier.send.call_args[1]
        assert call_kwargs["event_type"] == "post_mortem"

    async def test_postmortem_message_contains_key_info(self):
        rows = [
            (42, "low_battery", "warning", "sensor.door_battery",
             "Battery at 15%", "notify_only", "notified", "2026-03-25T12:00:00"),
        ]
        w = _make_watchdog()
        w._db = self._make_db_with_rows(rows)
        await w._generate_pending_postmortems()
        msg = w._notifier.send.call_args[1]["message"]
        assert "low" in msg.lower() or "battery" in msg.lower() or "Post" in msg
