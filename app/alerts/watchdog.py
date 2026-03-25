"""
Self-healing watchdog — Fase 2 (Post-MVP).

Runs three independent background checks:
- Stale integrations: entities that haven't updated in N minutes
- Entity leaks: domain entity count grew > 20% since baseline
- Post-mortem reports: summarize auto-fix incidents after they resolve

All incidents logged to incident_log. Notifications sent via Notifier.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Optional

from app.observability.logger import get_logger

if TYPE_CHECKING:
    from app.config import AppConfig
    from app.database import Database
    from app.events.notifier import Notifier
    from app.ha.client import HAClient
    from app.ha.supervisor import SupervisorClient

logger = get_logger(__name__)

# How often to run each check (seconds)
_STALE_CHECK_INTERVAL = 15 * 60       # 15 minutes
_LEAK_CHECK_INTERVAL = 60 * 60        # 1 hour
_POSTMORTEM_CHECK_INTERVAL = 10 * 60  # 10 minutes

# Stale thresholds per domain prefix (seconds)
_STALE_THRESHOLDS: dict[str, int] = {
    "sensor": 60 * 60,          # 1h
    "binary_sensor": 4 * 60 * 60,  # 4h (state-based, may not update often)
    "climate": 30 * 60,
    "weather": 2 * 60 * 60,
}
_DEFAULT_STALE_THRESHOLD = 2 * 60 * 60  # 2h

# Entity count growth threshold that triggers a leak alert
_LEAK_GROWTH_THRESHOLD = 0.20  # 20%

_INSERT_INCIDENT = """
    INSERT INTO incident_log (
        incident_type, severity, description, detection_method,
        auto_fix_action, auto_fix_result, affected_entities,
        root_cause, suggestion, post_mortem_sent
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
"""


class SelfHealingWatchdog:
    def __init__(
        self,
        config: "AppConfig",
        ha_client: "HAClient",
        supervisor_client: "SupervisorClient",
        db: "Database",
        notifier: "Notifier",
    ) -> None:
        self._config = config
        self._ha = ha_client
        self._sup = supervisor_client
        self._db = db
        self._notifier = notifier

        # Baseline domain counts (set on first leak check)
        self._domain_baseline: dict[str, int] = {}
        self._baseline_set_at: Optional[float] = None

        self._tasks: list[asyncio.Task] = []

    async def start(self) -> None:
        self._tasks = [
            asyncio.create_task(self._run_stale_check(), name="watchdog_stale"),
            asyncio.create_task(self._run_leak_check(), name="watchdog_leak"),
            asyncio.create_task(self._run_postmortem(), name="watchdog_postmortem"),
        ]
        logger.info("watchdog_started")

    async def stop(self) -> None:
        for task in self._tasks:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        self._tasks.clear()
        logger.info("watchdog_stopped")

    # ------------------------------------------------------------------ #
    # Stale integration check
    # ------------------------------------------------------------------ #

    async def _run_stale_check(self) -> None:
        while True:
            await asyncio.sleep(_STALE_CHECK_INTERVAL)
            try:
                await self._check_stale_integrations()
            except Exception as exc:
                logger.error("watchdog_stale_error", error=str(exc))

    async def _check_stale_integrations(self) -> None:
        try:
            states = await self._ha.get_states()
        except Exception as exc:
            logger.warning("watchdog_stale_get_states_failed", error=str(exc))
            return

        now = datetime.now(timezone.utc)
        stale_by_domain: dict[str, list[str]] = {}

        for s in states:
            eid = s.get("entity_id", "")
            domain = eid.split(".")[0]
            last_updated_str = s.get("last_updated") or s.get("last_changed")
            if not last_updated_str:
                continue
            try:
                # HA returns ISO format: "2026-03-24T10:30:00.123456+00:00"
                last_updated = datetime.fromisoformat(
                    last_updated_str.replace("Z", "+00:00")
                )
                age_seconds = (now - last_updated).total_seconds()
            except (ValueError, TypeError):
                continue

            threshold = _STALE_THRESHOLDS.get(domain, _DEFAULT_STALE_THRESHOLD)
            if age_seconds > threshold:
                stale_by_domain.setdefault(domain, []).append(eid)

        for domain, entities in stale_by_domain.items():
            if len(entities) < 2:
                # Single stale entity is normal; alert only if a domain has ≥2 stale
                continue
            description = (
                f"{len(entities)} {domain} entities haven't updated in >"
                f" {_STALE_THRESHOLDS.get(domain, _DEFAULT_STALE_THRESHOLD) // 60} min"
            )
            affected = ", ".join(entities[:5]) + ("..." if len(entities) > 5 else "")
            suggestion = (
                f"Check {domain} integration in HA → Settings → Devices & Services. "
                f"Consider reloading the integration."
            )

            await self._log_incident(
                incident_type="stale_integration",
                severity="warning",
                description=description,
                detection_method="watchdog_stale_check",
                affected_entities=affected,
                suggestion=suggestion,
            )

            msg = (
                f"⚠️ *Stale integration detected*\n"
                f"{len(entities)} `{domain}` entities haven't reported state changes\\.\n"
                f"Sample: `{entities[0]}`"
            )
            await self._notifier.send(
                event_type="stale_integration",
                entity_id=None,
                message=msg,
            )
            logger.warning("stale_integration_detected", domain=domain, count=len(entities))

    # ------------------------------------------------------------------ #
    # Entity leak check
    # ------------------------------------------------------------------ #

    async def _run_leak_check(self) -> None:
        # Let the system stabilize before first check
        await asyncio.sleep(60)
        while True:
            try:
                await self._check_entity_leaks()
            except Exception as exc:
                logger.error("watchdog_leak_error", error=str(exc))
            await asyncio.sleep(_LEAK_CHECK_INTERVAL)

    async def _check_entity_leaks(self) -> None:
        try:
            states = await self._ha.get_states()
        except Exception as exc:
            logger.warning("watchdog_leak_get_states_failed", error=str(exc))
            return

        # Count entities per domain
        current: dict[str, int] = {}
        for s in states:
            domain = s.get("entity_id", "?").split(".")[0]
            current[domain] = current.get(domain, 0) + 1

        import time
        now = time.monotonic()

        # First run: set baseline
        if not self._domain_baseline:
            self._domain_baseline = current.copy()
            self._baseline_set_at = now
            logger.info("watchdog_leak_baseline_set", domains=len(current))
            return

        # Reset baseline after 24h to avoid false positives from legitimate growth
        if self._baseline_set_at and (now - self._baseline_set_at) > 86400:
            self._domain_baseline = current.copy()
            self._baseline_set_at = now
            return

        # Detect leaks
        for domain, count in current.items():
            baseline = self._domain_baseline.get(domain, count)
            if baseline == 0:
                continue
            growth = (count - baseline) / baseline
            if growth > _LEAK_GROWTH_THRESHOLD:
                description = (
                    f"Entity count for '{domain}' grew {growth*100:.0f}% "
                    f"({baseline} → {count} entities)"
                )
                suggestion = (
                    f"Check if a {domain} integration is creating duplicate entities. "
                    f"Review HA entity registry for orphaned entries."
                )
                await self._log_incident(
                    incident_type="entity_leak",
                    severity="warning",
                    description=description,
                    detection_method="watchdog_entity_leak",
                    suggestion=suggestion,
                )
                msg = (
                    f"⚠️ *Entity count spike*\n"
                    f"`{domain}`: {baseline} → {count} entities "
                    f"\\({growth*100:.0f}% growth\\)"
                )
                await self._notifier.send(
                    event_type="entity_leak",
                    entity_id=None,
                    message=msg,
                )
                logger.warning(
                    "entity_leak_detected",
                    domain=domain,
                    baseline=baseline,
                    current=count,
                    growth_pct=f"{growth*100:.1f}%",
                )
                # Update baseline so we don't alert repeatedly for the same growth
                self._domain_baseline[domain] = count

    # ------------------------------------------------------------------ #
    # Post-mortem reports
    # ------------------------------------------------------------------ #

    async def _run_postmortem(self) -> None:
        while True:
            await asyncio.sleep(_POSTMORTEM_CHECK_INTERVAL)
            try:
                await self._generate_pending_postmortems()
            except Exception as exc:
                logger.error("watchdog_postmortem_error", error=str(exc))

    async def _generate_pending_postmortems(self) -> None:
        """
        Scan alert_log for auto-fix events that haven't had a post-mortem.
        Generate a structured summary and write it to incident_log.
        """
        cursor = await self._db.conn.execute(
            """
            SELECT id, alert_type, severity, entity_id, description,
                   auto_fix_action, auto_fix_result, timestamp
            FROM alert_log
            WHERE auto_fix_attempted = 1
              AND auto_fix_action IS NOT NULL
              AND id NOT IN (
                  SELECT COALESCE(CAST(json_extract(suggestion, '$.alert_log_id') AS INTEGER), -1)
                  FROM incident_log
                  WHERE incident_type = 'post_mortem'
              )
            ORDER BY timestamp DESC
            LIMIT 10
            """
        )
        rows = await cursor.fetchall()

        for row in rows:
            alert_id, alert_type, severity, entity_id, description, fix_action, fix_result, ts = (
                row[0], row[1], row[2], row[3], row[4], row[5], row[6], row[7]
            )
            await self._write_postmortem(
                alert_id=alert_id,
                alert_type=alert_type,
                severity=severity,
                entity_id=entity_id,
                description=description,
                fix_action=fix_action,
                fix_result=fix_result,
                timestamp=ts,
            )

    async def _write_postmortem(
        self,
        alert_id: int,
        alert_type: str,
        severity: str,
        entity_id: Optional[str],
        description: str,
        fix_action: str,
        fix_result: str,
        timestamp: str,
    ) -> None:
        import json

        entity_str = entity_id or "system"
        suggestion_data = json.dumps({"alert_log_id": alert_id})

        postmortem_desc = (
            f"Post-mortem: {alert_type} on {entity_str} at {timestamp[:16]} UTC. "
            f"Auto-fix applied: {fix_action}. Result: {fix_result}."
        )
        root_cause = (
            f"Alert type: {alert_type}. Triggered by: {description}"
        )

        await self._db.conn.execute(
            _INSERT_INCIDENT,
            (
                "post_mortem",
                severity,
                postmortem_desc,
                "watchdog_postmortem",
                fix_action,
                fix_result,
                entity_str,
                root_cause,
                suggestion_data,  # stores alert_log_id for dedup
                True,
            ),
        )
        await self._db.conn.commit()

        # Send Telegram post-mortem
        icon = "🚨" if severity == "critical" else "⚠️"
        msg = (
            f"📋 *Post\\-Mortem: {_escape(alert_type)}*\n"
            f"├ Detected: {_escape(timestamp[:16].replace('T', ' '))} UTC\n"
            f"├ Auto\\-fix: {_escape(fix_action)}\n"
            f"├ Result: {_escape(fix_result)}\n"
            f"├ Affected: `{_escape(entity_str)}`\n"
            f"└ Cause: {_escape(description)}"
        )
        await self._notifier.send(
            event_type="post_mortem",
            entity_id=entity_id,
            message=msg,
        )
        logger.info("postmortem_sent", alert_id=alert_id, alert_type=alert_type)

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #

    async def _log_incident(
        self,
        incident_type: str,
        severity: str,
        description: str,
        detection_method: str,
        auto_fix_action: Optional[str] = None,
        auto_fix_result: Optional[str] = None,
        affected_entities: Optional[str] = None,
        root_cause: Optional[str] = None,
        suggestion: Optional[str] = None,
    ) -> None:
        try:
            await self._db.conn.execute(
                _INSERT_INCIDENT,
                (
                    incident_type, severity, description, detection_method,
                    auto_fix_action, auto_fix_result, affected_entities,
                    root_cause, suggestion, False,
                ),
            )
            await self._db.conn.commit()
        except Exception as exc:
            logger.error("watchdog_log_incident_failed", error=str(exc))


def _escape(text: str) -> str:
    """Minimal MarkdownV2 escape for watchdog messages."""
    import re
    return re.sub(r"([_*\[\]()~`>#+=|{}.!\\-])", r"\\\1", str(text))
