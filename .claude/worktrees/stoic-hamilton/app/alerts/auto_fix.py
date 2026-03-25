"""
Risk-scored auto-remediation.
Only actions with risk_score <= config.auto_fix_max_risk_score are applied automatically.
All auto-fixes are logged. A backup is created before risk >= 3 actions.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from app.observability.logger import get_logger
from app.schemas.alert_config import AlertEvent, AlertType

if TYPE_CHECKING:
    from app.config import AppConfig
    from app.ha.supervisor import SupervisorClient

logger = get_logger(__name__)


class AutoFix:
    def __init__(self, config: "AppConfig", supervisor_client: "SupervisorClient") -> None:
        self._config = config
        self._sup = supervisor_client

    def can_fix(self, alert: AlertEvent) -> bool:
        """Return True if we have an auto-fix and it's within the configured risk limit."""
        action = self._fix_action(alert)
        if not action:
            return False
        risk = self._fix_risk(alert)
        return risk <= self._config.auto_fix_max_risk_score

    async def apply(self, alert: AlertEvent) -> tuple[str, str] | None:
        """
        Execute the auto-fix.
        Returns (action_description, result) or None if no fix available.
        """
        action_desc = self._fix_action(alert)
        if not action_desc:
            return None

        risk = self._fix_risk(alert)
        if risk > self._config.auto_fix_max_risk_score:
            return None

        # Backup before medium+ risk fixes
        if risk >= 3:
            try:
                await self._sup.create_backup()
                logger.info("auto_fix_backup_created", alert_type=alert.alert_type)
            except Exception as exc:
                logger.error("auto_fix_backup_failed", error=str(exc))

        try:
            result = await self._execute_fix(alert)
            logger.info(
                "auto_fix_applied",
                alert_type=alert.alert_type.value,
                entity_id=alert.entity_id,
                action=action_desc,
                risk=risk,
            )
            return action_desc, result
        except Exception as exc:
            logger.error(
                "auto_fix_failed",
                alert_type=alert.alert_type.value,
                error=str(exc),
            )
            return action_desc, f"failed: {exc}"

    # ------------------------------------------------------------------ #

    def _fix_action(self, alert: AlertEvent) -> str | None:
        """Human-readable description of the fix, or None if unfixable."""
        if alert.alert_type == AlertType.DEVICE_UNAVAILABLE and alert.entity_id:
            domain = alert.entity_id.split(".")[0]
            # Only attempt reload for known integration domains
            if domain in ("zwave_js", "zigbee2mqtt", "mqtt", "modbus"):
                return f"Reload integration: {domain}"
        return None

    def _fix_risk(self, alert: AlertEvent) -> int:
        """Risk score for the auto-fix action."""
        if alert.alert_type == AlertType.DEVICE_UNAVAILABLE:
            return 2  # reload integration = LOW risk
        return 5  # unknown = CRITICAL, never auto-applied

    async def _execute_fix(self, alert: AlertEvent) -> str:
        if alert.alert_type == AlertType.DEVICE_UNAVAILABLE and alert.entity_id:
            domain = alert.entity_id.split(".")[0]
            await self._sup._request("POST", f"/core/api/services/{domain}/reload")
            return "Reload triggered."
        return "No action taken."
