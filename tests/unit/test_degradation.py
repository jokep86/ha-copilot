"""
Unit tests for DegradationMap (circuit breaker + health tracking).
"""
from __future__ import annotations

import pytest

from app.core.degradation import ComponentHealth, DegradationMap


@pytest.fixture
def deg() -> DegradationMap:
    return DegradationMap()


def test_all_healthy_on_init(deg: DegradationMap) -> None:
    for comp in deg.COMPONENTS:
        assert deg.is_healthy(comp)


def test_set_degraded(deg: DegradationMap) -> None:
    deg.set_degraded("ha_api", "timeout")
    assert deg.get("ha_api") == ComponentHealth.DEGRADED
    assert not deg.is_healthy("ha_api")
    assert deg.is_available("ha_api")


def test_set_unavailable(deg: DegradationMap) -> None:
    deg.set_unavailable("ha_api", "down")
    assert deg.get("ha_api") == ComponentHealth.UNAVAILABLE
    assert not deg.is_available("ha_api")


def test_set_healthy_clears_state(deg: DegradationMap) -> None:
    deg.set_unavailable("ha_api", "down")
    deg.set_healthy("ha_api")
    assert deg.is_healthy("ha_api")
    assert deg.last_error("ha_api") is None


def test_circuit_breaker_opens_after_3_failures(deg: DegradationMap) -> None:
    deg.record_failure("ha_api", "timeout")
    assert deg.get("ha_api") == ComponentHealth.DEGRADED
    deg.record_failure("ha_api", "timeout")
    assert deg.get("ha_api") == ComponentHealth.DEGRADED
    deg.record_failure("ha_api", "timeout")
    assert deg.get("ha_api") == ComponentHealth.UNAVAILABLE


def test_recovery_resets_failure_count(deg: DegradationMap) -> None:
    deg.record_failure("ha_api", "err")
    deg.record_failure("ha_api", "err")
    deg.set_healthy("ha_api")
    # Should start fresh — only 1 more failure to degraded
    deg.record_failure("ha_api", "err")
    assert deg.get("ha_api") == ComponentHealth.DEGRADED


def test_status_emoji(deg: DegradationMap) -> None:
    assert deg.status_emoji("ha_api") == "🟢"
    deg.set_degraded("ha_api", "slow")
    assert deg.status_emoji("ha_api") == "🟡"
    deg.set_unavailable("ha_api", "down")
    assert deg.status_emoji("ha_api") == "🔴"


def test_summary_returns_all_components(deg: DegradationMap) -> None:
    summary = deg.summary
    assert set(summary.keys()) == set(deg.COMPONENTS)


def test_all_healthy_property(deg: DegradationMap) -> None:
    assert deg.all_healthy is True
    deg.set_degraded("claude", "rate_limit")
    assert deg.all_healthy is False
