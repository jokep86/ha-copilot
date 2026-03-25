"""
Health Pulse and Dead Man's Switch.

Health Pulse: emits a "still alive" log every N seconds (configurable).
Dead Man's Switch: if not reset within M seconds, calls sys.exit(1)
  so Supervisor watchdog restarts the add-on.
"""
from __future__ import annotations

import asyncio
import sys
import time

from app.observability.logger import get_logger

logger = get_logger(__name__)


class HealthPulse:
    """Emits periodic heartbeat log entries."""

    def __init__(self, interval_seconds: int = 300) -> None:
        self.interval = interval_seconds
        self._task: asyncio.Task | None = None
        self._start_time = time.monotonic()

    async def start(self) -> None:
        self._task = asyncio.create_task(self._run(), name="health_pulse")
        logger.info("health_pulse_started", interval_seconds=self.interval)

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def _run(self) -> None:
        while True:
            await asyncio.sleep(self.interval)
            uptime = int(time.monotonic() - self._start_time)
            logger.info("health_pulse", uptime_seconds=uptime, status="alive")


class DeadManSwitch:
    """
    Triggers sys.exit(1) if not reset within timeout_seconds.
    Supervisor watchdog restarts the add-on automatically.
    Call reset() on every successfully processed command.
    """

    def __init__(self, timeout_seconds: int = 600) -> None:
        self.timeout = timeout_seconds
        self._last_reset = time.monotonic()
        self._task: asyncio.Task | None = None

    def reset(self) -> None:
        """Reset the switch — call on every processed command."""
        self._last_reset = time.monotonic()

    async def start(self) -> None:
        self._task = asyncio.create_task(self._run(), name="dead_man_switch")
        logger.info("dead_man_switch_started", timeout_seconds=self.timeout)

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def _run(self) -> None:
        check_interval = min(30, self.timeout // 4)
        while True:
            await asyncio.sleep(check_interval)
            elapsed = time.monotonic() - self._last_reset
            if elapsed > self.timeout:
                logger.critical(
                    "dead_man_switch_triggered",
                    elapsed_seconds=int(elapsed),
                    timeout_seconds=self.timeout,
                )
                sys.exit(1)
