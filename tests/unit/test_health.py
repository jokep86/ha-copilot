"""
Unit tests for HealthPulse and DeadManSwitch.
"""
from __future__ import annotations

import asyncio
import time
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from app.observability.health import DeadManSwitch, HealthPulse


class TestHealthPulse:
    async def test_start_creates_task(self):
        pulse = HealthPulse(interval_seconds=300)
        await pulse.start()
        assert pulse._task is not None
        await pulse.stop()

    async def test_stop_cancels_task(self):
        pulse = HealthPulse(interval_seconds=300)
        await pulse.start()
        await pulse.stop()
        assert pulse._task.cancelled() or pulse._task.done()

    async def test_stop_before_start_is_noop(self):
        pulse = HealthPulse(interval_seconds=300)
        await pulse.stop()  # Should not raise

    async def test_interval_stored(self):
        pulse = HealthPulse(interval_seconds=120)
        assert pulse.interval == 120

    async def test_default_interval(self):
        pulse = HealthPulse()
        assert pulse.interval == 300

    async def test_pulse_fires_after_interval(self):
        pulse = HealthPulse(interval_seconds=1)
        log_calls = []

        with patch("app.observability.health.logger") as mock_logger:
            mock_logger.info = MagicMock(side_effect=lambda *a, **kw: log_calls.append(kw))
            await pulse.start()
            await asyncio.sleep(1.2)
            await pulse.stop()

        # At least one pulse should have fired
        pulse_events = [c for c in log_calls if c.get("status") == "alive"]
        assert len(pulse_events) >= 1

    async def test_double_stop_is_safe(self):
        pulse = HealthPulse(interval_seconds=300)
        await pulse.start()
        await pulse.stop()
        await pulse.stop()  # Should not raise


class TestDeadManSwitch:
    async def test_start_creates_task(self):
        dms = DeadManSwitch(timeout_seconds=600)
        await dms.start()
        assert dms._task is not None
        await dms.stop()

    async def test_stop_cancels_task(self):
        dms = DeadManSwitch(timeout_seconds=600)
        await dms.start()
        await dms.stop()
        assert dms._task.cancelled() or dms._task.done()

    async def test_stop_before_start_is_noop(self):
        dms = DeadManSwitch(timeout_seconds=600)
        await dms.stop()

    async def test_reset_updates_last_reset(self):
        dms = DeadManSwitch(timeout_seconds=600)
        old = dms._last_reset
        await asyncio.sleep(0.01)
        dms.reset()
        assert dms._last_reset > old

    async def test_default_timeout(self):
        dms = DeadManSwitch()
        assert dms.timeout == 600

    async def test_custom_timeout(self):
        dms = DeadManSwitch(timeout_seconds=120)
        assert dms.timeout == 120

    async def test_triggers_sys_exit_on_timeout(self):
        # Use a very short timeout to test the trigger
        dms = DeadManSwitch(timeout_seconds=1)
        exited = []

        with patch("app.observability.health.sys.exit", side_effect=lambda code: exited.append(code)):
            await dms.start()
            # Don't reset — let it time out
            await asyncio.sleep(1.5)
            await dms.stop()

        # sys.exit(1) should have been called at least once
        assert 1 in exited

    async def test_no_exit_when_reset_frequently(self):
        dms = DeadManSwitch(timeout_seconds=1)
        exited = []

        with patch("app.observability.health.sys.exit", side_effect=lambda code: exited.append(code)):
            await dms.start()
            # Reset faster than timeout
            for _ in range(5):
                dms.reset()
                await asyncio.sleep(0.1)
            await dms.stop()

        assert exited == []

    async def test_double_stop_is_safe(self):
        dms = DeadManSwitch(timeout_seconds=600)
        await dms.start()
        await dms.stop()
        await dms.stop()  # Should not raise
