"""
Graceful degradation map + component health tracking (see ADR-013).

Components: ha_api, supervisor_api, websocket, telegram, claude, database.
States: healthy → degraded → unavailable.
Circuit breaker: 3 consecutive failures → circuit open (unavailable).
"""
from __future__ import annotations

from enum import Enum
from typing import Optional

from app.observability.logger import get_logger

logger = get_logger(__name__)

CIRCUIT_BREAKER_THRESHOLD = 3


class ComponentHealth(str, Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNAVAILABLE = "unavailable"


class DegradationMap:
    """Tracks health state for all system components."""

    COMPONENTS = [
        "ha_api",
        "supervisor_api",
        "websocket",
        "telegram",
        "claude",
        "database",
    ]

    # Degraded behavior descriptions (for /sys output)
    DEGRADED_BEHAVIOR: dict[str, str] = {
        "ha_api": "All HA commands fail. Retrying with backoff.",
        "supervisor_api": "System/addon commands unavailable. Device control via HA API still works.",
        "websocket": "Proactive notifications paused. Entity cache uses TTL.",
        "telegram": "Cannot send messages. Queuing locally.",
        "claude": "AI unavailable. Use /help for structured commands.",
        "database": "Recreating empty DB. Audit log lost.",
    }

    def __init__(self) -> None:
        self._health: dict[str, ComponentHealth] = {
            c: ComponentHealth.HEALTHY for c in self.COMPONENTS
        }
        self._last_error: dict[str, Optional[str]] = {c: None for c in self.COMPONENTS}
        self._failure_count: dict[str, int] = {c: 0 for c in self.COMPONENTS}

    def set_healthy(self, component: str) -> None:
        prev = self._health.get(component)
        self._health[component] = ComponentHealth.HEALTHY
        self._failure_count[component] = 0
        self._last_error[component] = None
        if prev != ComponentHealth.HEALTHY:
            logger.info("component_recovered", component=component)

    def set_degraded(self, component: str, reason: str) -> None:
        self._health[component] = ComponentHealth.DEGRADED
        self._last_error[component] = reason
        logger.warning("component_degraded", component=component, reason=reason)

    def set_unavailable(self, component: str, reason: str) -> None:
        self._health[component] = ComponentHealth.UNAVAILABLE
        self._last_error[component] = reason
        logger.error("component_unavailable", component=component, reason=reason)

    def record_failure(self, component: str, reason: str) -> None:
        """Increment failure counter. Opens circuit after threshold consecutive failures."""
        self._failure_count[component] = self._failure_count.get(component, 0) + 1
        count = self._failure_count[component]
        if count >= CIRCUIT_BREAKER_THRESHOLD:
            self.set_unavailable(
                component, f"circuit_open after {count} failures: {reason}"
            )
            logger.critical(
                "circuit_breaker_open",
                component=component,
                failures=count,
                reason=reason,
            )
        else:
            self.set_degraded(component, reason)

    def get(self, component: str) -> ComponentHealth:
        return self._health.get(component, ComponentHealth.UNAVAILABLE)

    def is_healthy(self, component: str) -> bool:
        return self._health.get(component) == ComponentHealth.HEALTHY

    def is_available(self, component: str) -> bool:
        return self._health.get(component) != ComponentHealth.UNAVAILABLE

    def last_error(self, component: str) -> Optional[str]:
        return self._last_error.get(component)

    def status_emoji(self, component: str) -> str:
        return {
            ComponentHealth.HEALTHY: "🟢",
            ComponentHealth.DEGRADED: "🟡",
            ComponentHealth.UNAVAILABLE: "🔴",
        }.get(self._health.get(component, ComponentHealth.UNAVAILABLE), "⚪")

    @property
    def summary(self) -> dict[str, str]:
        return {c: h.value for c, h in self._health.items()}

    @property
    def all_healthy(self) -> bool:
        return all(h == ComponentHealth.HEALTHY for h in self._health.values())
