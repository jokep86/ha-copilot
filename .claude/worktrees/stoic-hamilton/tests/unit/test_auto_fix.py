"""
Unit tests for AutoFix.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
import pytest

from app.alerts.auto_fix import AutoFix
from app.schemas.alert_config import AlertEvent, AlertType


def _config(max_risk=1):
    cfg = MagicMock()
    cfg.auto_fix_max_risk_score = max_risk
    return cfg


def _alert(alert_type=AlertType.DEVICE_UNAVAILABLE, entity_id="zwave_js.sensor_1"):
    return AlertEvent(
        alert_type=alert_type,
        severity="warning",
        entity_id=entity_id,
        description="Test alert",
        risk_score=0,
    )


class TestAutoFix:
    def test_can_fix_zwave_within_limit(self):
        fix = AutoFix(_config(max_risk=2), MagicMock())
        assert fix.can_fix(_alert(entity_id="zwave_js.sensor")) is True

    def test_cannot_fix_above_limit(self):
        fix = AutoFix(_config(max_risk=0), MagicMock())
        assert fix.can_fix(_alert(entity_id="zwave_js.sensor")) is False

    def test_cannot_fix_unknown_domain(self):
        fix = AutoFix(_config(max_risk=5), MagicMock())
        assert fix.can_fix(_alert(entity_id="light.sala")) is False

    def test_cannot_fix_low_battery(self):
        fix = AutoFix(_config(max_risk=5), MagicMock())
        a = AlertEvent(
            alert_type=AlertType.LOW_BATTERY,
            severity="warning",
            entity_id="sensor.battery",
            description="Low battery",
            risk_score=0,
        )
        assert fix.can_fix(a) is False

    async def test_apply_returns_none_when_unfixable(self):
        fix = AutoFix(_config(max_risk=5), MagicMock())
        result = await fix.apply(_alert(entity_id="light.sala"))
        assert result is None

    async def test_apply_returns_none_above_risk_limit(self):
        fix = AutoFix(_config(max_risk=0), MagicMock())
        result = await fix.apply(_alert(entity_id="zwave_js.sensor"))
        assert result is None
