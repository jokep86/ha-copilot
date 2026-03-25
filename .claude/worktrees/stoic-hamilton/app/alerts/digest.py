"""
Daily health digest — sends a summary at the configured time each day.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from app.observability.logger import get_logger

if TYPE_CHECKING:
    from app.alerts.engine import AlertEngine
    from app.config import AppConfig
    from app.core.degradation import DegradationMap
    from app.events.notifier import Notifier

logger = get_logger(__name__)


class DailyDigest:
    def __init__(
        self,
        config: "AppConfig",
        alert_engine: "AlertEngine",
        notifier: "Notifier",
        degradation: "DegradationMap",
    ) -> None:
        self._config = config
        self._engine = alert_engine
        self._notifier = notifier
        self._degradation = degradation
        self._task: asyncio.Task | None = None

    async def start(self) -> None:
        if not self._config.daily_digest_enabled:
            return
        self._task = asyncio.create_task(self._run(), name="daily_digest")
        logger.info("daily_digest_started", time=self._config.daily_digest_time)

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def _run(self) -> None:
        while True:
            seconds_until = self._seconds_until_next()
            await asyncio.sleep(seconds_until)
            try:
                await self._send()
            except Exception as exc:
                logger.error("daily_digest_failed", error=str(exc))

    def _seconds_until_next(self) -> float:
        """Seconds until the next configured digest time (HH:MM)."""
        try:
            h, m = map(int, self._config.daily_digest_time.split(":"))
        except Exception:
            return 3600  # fallback: 1 hour

        now = datetime.now(timezone.utc)
        target = now.replace(hour=h, minute=m, second=0, microsecond=0)
        if target <= now:
            # Already passed today — schedule for tomorrow
            from datetime import timedelta
            target += timedelta(days=1)
        return (target - now).total_seconds()

    async def _send(self) -> None:
        recent = await self._engine.get_recent(50)
        total = len(recent)
        critical = sum(1 for a in recent if a["severity"] == "critical")
        warning = sum(1 for a in recent if a["severity"] == "warning")
        fixed = sum(1 for a in recent if a["auto_fix_attempted"])

        deg_summary = self._degradation.summary
        healthy = sum(1 for v in deg_summary.values() if v == "healthy")
        total_components = len(deg_summary)

        lines = [
            "📋 *Daily Digest*",
            "",
            f"🕐 {datetime.now(timezone.utc).strftime('%Y\\-%-m\\-%-d %H:%M')} UTC",
            "",
            f"*Components:* {healthy}/{total_components} healthy",
        ]

        for comp, state in deg_summary.items():
            emoji = self._degradation.status_emoji(comp)
            lines.append(f"  {emoji} {comp}")

        lines += [
            "",
            f"*Alerts \\(last 24h\\):* {total} total, {critical} critical, {warning} warnings",
        ]
        if fixed:
            lines.append(f"*Auto\\-fixes applied:* {fixed}")

        if critical == 0 and warning == 0:
            lines.append("✅ No issues detected\\!")

        await self._notifier.send(
            event_type="daily_digest",
            entity_id=None,
            message="\n".join(lines),
        )
        logger.info("daily_digest_sent", alerts=total, critical=critical)
