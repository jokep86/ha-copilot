"""
Alert engine — periodic health check runner.
Runs every health_check_interval_seconds, evaluates all enabled alert conditions,
logs to alert_log, sends notifications, and applies auto-fixes within risk limit.
"""
from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from app.alerts.auto_fix import AutoFix
from app.alerts.conditions import AlertConditionChecker
from app.observability.logger import get_logger
from app.schemas.alert_config import AlertEvent

if TYPE_CHECKING:
    from app.config import AppConfig
    from app.database import Database
    from app.events.notifier import Notifier
    from app.ha.client import HAClient
    from app.ha.discovery import EntityDiscovery
    from app.ha.supervisor import SupervisorClient

logger = get_logger(__name__)

_INSERT_ALERT = """
    INSERT INTO alert_log (
        alert_type, severity, entity_id, description, risk_score,
        auto_fix_attempted, auto_fix_action, auto_fix_result, acknowledged
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0)
"""

_SELECT_RECENT = """
    SELECT alert_type, severity, entity_id, description, risk_score,
           auto_fix_attempted, auto_fix_action, auto_fix_result, timestamp
    FROM alert_log
    ORDER BY timestamp DESC
    LIMIT ?
"""

_COOLDOWN_CHECK = """
    SELECT COUNT(*) FROM alert_log
    WHERE alert_type = ?
      AND (entity_id = ? OR (entity_id IS NULL AND ? IS NULL))
      AND datetime(timestamp, '+' || ? || ' seconds') > datetime('now')
"""


class AlertEngine:
    def __init__(
        self,
        config: "AppConfig",
        ha_client: "HAClient",
        supervisor_client: "SupervisorClient",
        discovery: "EntityDiscovery",
        db: "Database",
        notifier: "Notifier",
    ) -> None:
        self._config = config
        self._db = db
        self._notifier = notifier
        self._checker = AlertConditionChecker(
            config=config,
            ha_client=ha_client,
            supervisor_client=supervisor_client,
            discovery=discovery,
        )
        self._auto_fix = AutoFix(config=config, supervisor_client=supervisor_client)
        self._task: asyncio.Task | None = None

    async def start(self) -> None:
        self._task = asyncio.create_task(self._run(), name="alert_engine")
        logger.info(
            "alert_engine_started",
            interval=self._config.health_check_interval_seconds,
        )

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("alert_engine_stopped")

    async def get_recent(self, n: int = 20) -> list[dict]:
        cursor = await self._db.conn.execute(_SELECT_RECENT, (n,))
        rows = await cursor.fetchall()
        return [
            {
                "alert_type": r[0], "severity": r[1], "entity_id": r[2],
                "description": r[3], "risk_score": r[4],
                "auto_fix_attempted": bool(r[5]), "auto_fix_action": r[6],
                "auto_fix_result": r[7], "timestamp": r[8],
            }
            for r in rows
        ]

    # ------------------------------------------------------------------ #

    async def _run(self) -> None:
        interval = self._config.health_check_interval_seconds
        while True:
            await asyncio.sleep(interval)
            try:
                await self._check_all()
            except Exception as exc:
                logger.error("alert_engine_check_error", error=str(exc))

    async def _check_all(self) -> None:
        alerts = await self._checker.check_all()
        for alert in alerts:
            await self._process_alert(alert)

    async def _process_alert(self, alert: AlertEvent) -> None:
        # Check cooldown from alert_log
        cond = self._get_condition_config(alert.alert_type.value)
        cooldown = cond.cooldown_seconds if cond else 300

        if await self._in_cooldown(alert, cooldown):
            return

        # Auto-fix
        fix_attempted = False
        fix_action = None
        fix_result = None

        if self._auto_fix.can_fix(alert):
            fix_attempted = True
            fix = await self._auto_fix.apply(alert)
            if fix:
                fix_action, fix_result = fix

        # Log to alert_log
        try:
            await self._db.conn.execute(
                _INSERT_ALERT,
                (
                    alert.alert_type.value,
                    alert.severity,
                    alert.entity_id,
                    alert.description,
                    alert.risk_score,
                    fix_attempted,
                    fix_action,
                    fix_result,
                ),
            )
            await self._db.conn.commit()
        except Exception as exc:
            logger.error("alert_log_insert_failed", error=str(exc))

        # Send notification
        icon = {"critical": "🚨", "warning": "⚠️", "info": "ℹ️"}.get(alert.severity, "🔔")
        msg = f"{icon} *Alert*: {alert.description}"
        if fix_action and fix_result:
            msg += f"\n✅ Auto\\-fix: {fix_action} → {fix_result}"

        await self._notifier.send(
            event_type=alert.alert_type.value,
            entity_id=alert.entity_id,
            message=msg,
            was_auto_fix=fix_attempted,
            fix_action=fix_action,
            fix_result=fix_result,
        )

        logger.info(
            "alert_processed",
            alert_type=alert.alert_type.value,
            severity=alert.severity,
            entity_id=alert.entity_id,
            auto_fix=fix_attempted,
        )

    async def _in_cooldown(self, alert: AlertEvent, cooldown: int) -> bool:
        try:
            cursor = await self._db.conn.execute(
                _COOLDOWN_CHECK,
                (alert.alert_type.value, alert.entity_id, alert.entity_id, cooldown),
            )
            row = await cursor.fetchone()
            return bool(row and row[0] > 0)
        except Exception:
            return False

    def _get_condition_config(self, alert_type: str):
        for cond in self._config.alert_conditions:
            if cond.type == alert_type:
                return cond
        return None
