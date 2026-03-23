"""
Alert condition evaluators.
Each checker receives current system state and returns AlertEvent | None.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from app.observability.logger import get_logger
from app.schemas.alert_config import AlertEvent, AlertType

if TYPE_CHECKING:
    from app.config import AppConfig, AlertConditionConfig
    from app.ha.client import HAClient
    from app.ha.discovery import EntityDiscovery
    from app.ha.supervisor import SupervisorClient

logger = get_logger(__name__)


class AlertConditionChecker:
    def __init__(
        self,
        config: "AppConfig",
        ha_client: "HAClient",
        supervisor_client: "SupervisorClient",
        discovery: "EntityDiscovery",
    ) -> None:
        self._config = config
        self._ha = ha_client
        self._sup = supervisor_client
        self._discovery = discovery

    async def check_all(self) -> list[AlertEvent]:
        """Run all enabled conditions and return triggered alerts."""
        alerts: list[AlertEvent] = []
        for cond in self._config.alert_conditions:
            if not cond.enabled:
                continue
            try:
                result = await self._check_condition(cond)
                alerts.extend(result)
            except Exception as exc:
                logger.error(
                    "alert_condition_check_failed",
                    condition=cond.type,
                    error=str(exc),
                )
        return alerts

    async def _check_condition(
        self, cond: "AlertConditionConfig"
    ) -> list[AlertEvent]:
        if cond.type == AlertType.DEVICE_UNAVAILABLE:
            return await self._check_device_unavailable()
        if cond.type == AlertType.LOW_BATTERY:
            return await self._check_low_battery(cond.threshold or 20.0)
        if cond.type == AlertType.DISK_USAGE:
            return await self._check_disk_usage(cond.threshold_percent or 85.0)
        return []

    # ------------------------------------------------------------------ #

    async def _check_device_unavailable(self) -> list[AlertEvent]:
        alerts = []
        try:
            states = await self._discovery.get_all_states()
        except Exception:
            return []

        for entity in states:
            if entity.get("state") == "unavailable":
                eid = entity.get("entity_id", "?")
                fname = entity.get("attributes", {}).get("friendly_name", eid)
                alerts.append(AlertEvent(
                    alert_type=AlertType.DEVICE_UNAVAILABLE,
                    severity="warning",
                    entity_id=eid,
                    description=f"Device unavailable: {fname}",
                    risk_score=0,
                ))
        return alerts

    async def _check_low_battery(self, threshold: float) -> list[AlertEvent]:
        alerts = []
        try:
            sensors = await self._discovery.get_entities_by_domain("sensor")
        except Exception:
            return []

        for entity in sensors:
            attrs = entity.get("attributes", {})
            if attrs.get("device_class") != "battery":
                continue
            try:
                level = float(entity.get("state", "100"))
            except ValueError:
                continue
            if level < threshold:
                eid = entity.get("entity_id", "?")
                fname = attrs.get("friendly_name", eid)
                alerts.append(AlertEvent(
                    alert_type=AlertType.LOW_BATTERY,
                    severity="warning",
                    entity_id=eid,
                    description=f"Low battery: {fname} at {level:.0f}%",
                    risk_score=0,
                ))
        return alerts

    async def _check_disk_usage(self, threshold_percent: float) -> list[AlertEvent]:
        try:
            host = await self._sup.get_host_info()
        except Exception:
            return []

        # Supervisor returns disk info under various keys depending on version
        disk_used = host.get("disk_used", 0)
        disk_total = host.get("disk_total", 0)
        if not disk_total:
            return []

        used_pct = (disk_used / disk_total) * 100
        if used_pct < threshold_percent:
            return []

        return [AlertEvent(
            alert_type=AlertType.DISK_USAGE,
            severity="critical" if used_pct >= 95 else "warning",
            entity_id=None,
            description=f"Disk usage {used_pct:.1f}% (threshold {threshold_percent:.0f}%)",
            risk_score=0,
        )]
