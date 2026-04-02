"""
Unit tests for AlertConditionChecker.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
import pytest

from app.alerts.conditions import AlertConditionChecker
from app.schemas.alert_config import AlertType


def _make_checker(states=None, sensors=None, host_info=None):
    config = MagicMock()
    config.alert_conditions = []

    ha = MagicMock()
    sup = MagicMock()
    sup.get_host_info = AsyncMock(return_value=host_info or {"disk_used": 50, "disk_total": 100})

    discovery = MagicMock()
    discovery.get_all_states = AsyncMock(return_value=states or [])
    discovery.get_entities_by_domain = AsyncMock(return_value=sensors or [])

    checker = AlertConditionChecker(config, ha, sup, discovery)
    return checker, config, ha, sup, discovery


def _cond(type_, enabled=True, threshold=None, threshold_percent=None, cooldown=300):
    c = MagicMock()
    c.type = type_
    c.enabled = enabled
    c.threshold = threshold
    c.threshold_percent = threshold_percent
    c.cooldown_seconds = cooldown
    return c


class TestAlertConditionChecker:
    async def test_check_all_no_conditions(self):
        checker, config, _, _, _ = _make_checker()
        config.alert_conditions = []
        result = await checker.check_all()
        assert result == []

    async def test_check_all_disabled_condition_skipped(self):
        checker, config, _, _, discovery = _make_checker(
            states=[{"entity_id": "light.x", "state": "unavailable", "attributes": {}}]
        )
        config.alert_conditions = [_cond(AlertType.DEVICE_UNAVAILABLE, enabled=False)]
        result = await checker.check_all()
        assert result == []

    async def test_check_all_exception_in_condition_skipped(self):
        checker, config, _, _, discovery = _make_checker()
        discovery.get_all_states = AsyncMock(side_effect=Exception("HA down"))
        config.alert_conditions = [_cond(AlertType.DEVICE_UNAVAILABLE)]
        # Should not raise, just return empty
        result = await checker.check_all()
        assert result == []

    async def test_device_unavailable_detected(self):
        states = [
            {"entity_id": "light.sala", "state": "unavailable", "attributes": {"friendly_name": "Sala"}},
            {"entity_id": "switch.fan", "state": "on", "attributes": {}},
        ]
        checker, config, _, _, _ = _make_checker(states=states)
        config.alert_conditions = [_cond(AlertType.DEVICE_UNAVAILABLE)]
        result = await checker.check_all()
        assert len(result) == 1
        assert result[0].alert_type == AlertType.DEVICE_UNAVAILABLE
        assert result[0].entity_id == "light.sala"
        assert "Sala" in result[0].description

    async def test_device_unavailable_none_when_all_available(self):
        states = [
            {"entity_id": "light.sala", "state": "on", "attributes": {}},
            {"entity_id": "switch.fan", "state": "off", "attributes": {}},
        ]
        checker, config, _, _, _ = _make_checker(states=states)
        config.alert_conditions = [_cond(AlertType.DEVICE_UNAVAILABLE)]
        result = await checker.check_all()
        assert result == []

    async def test_device_unavailable_multiple(self):
        states = [
            {"entity_id": "light.a", "state": "unavailable", "attributes": {}},
            {"entity_id": "light.b", "state": "unavailable", "attributes": {}},
        ]
        checker, config, _, _, _ = _make_checker(states=states)
        config.alert_conditions = [_cond(AlertType.DEVICE_UNAVAILABLE)]
        result = await checker.check_all()
        assert len(result) == 2

    async def test_low_battery_detected(self):
        sensors = [
            {
                "entity_id": "sensor.door_battery",
                "state": "15",
                "attributes": {"device_class": "battery", "friendly_name": "Door Battery"},
            },
            {
                "entity_id": "sensor.window_battery",
                "state": "80",
                "attributes": {"device_class": "battery", "friendly_name": "Window Battery"},
            },
        ]
        checker, config, _, _, _ = _make_checker(sensors=sensors)
        config.alert_conditions = [_cond(AlertType.LOW_BATTERY, threshold=20.0)]
        result = await checker.check_all()
        assert len(result) == 1
        assert result[0].entity_id == "sensor.door_battery"
        assert "15%" in result[0].description

    async def test_low_battery_uses_default_threshold_20(self):
        sensors = [
            {
                "entity_id": "sensor.bat",
                "state": "10",
                "attributes": {"device_class": "battery"},
            }
        ]
        checker, config, _, _, _ = _make_checker(sensors=sensors)
        config.alert_conditions = [_cond(AlertType.LOW_BATTERY, threshold=None)]
        result = await checker.check_all()
        assert len(result) == 1

    async def test_low_battery_non_battery_sensor_ignored(self):
        sensors = [
            {
                "entity_id": "sensor.temp",
                "state": "5",
                "attributes": {"device_class": "temperature"},
            }
        ]
        checker, config, _, _, _ = _make_checker(sensors=sensors)
        config.alert_conditions = [_cond(AlertType.LOW_BATTERY, threshold=20.0)]
        result = await checker.check_all()
        assert result == []

    async def test_low_battery_invalid_state_ignored(self):
        sensors = [
            {
                "entity_id": "sensor.bat",
                "state": "unknown",
                "attributes": {"device_class": "battery"},
            }
        ]
        checker, config, _, _, _ = _make_checker(sensors=sensors)
        config.alert_conditions = [_cond(AlertType.LOW_BATTERY, threshold=20.0)]
        result = await checker.check_all()
        assert result == []

    async def test_disk_usage_detected(self):
        host_info = {"disk_used": 92, "disk_total": 100}
        checker, config, _, _, _ = _make_checker(host_info=host_info)
        config.alert_conditions = [_cond(AlertType.DISK_USAGE, threshold_percent=85.0)]
        result = await checker.check_all()
        assert len(result) == 1
        assert result[0].alert_type == AlertType.DISK_USAGE
        assert "92.0%" in result[0].description

    async def test_disk_usage_critical_severity(self):
        host_info = {"disk_used": 96, "disk_total": 100}
        checker, config, _, _, _ = _make_checker(host_info=host_info)
        config.alert_conditions = [_cond(AlertType.DISK_USAGE, threshold_percent=85.0)]
        result = await checker.check_all()
        assert result[0].severity == "critical"

    async def test_disk_usage_warning_severity(self):
        host_info = {"disk_used": 90, "disk_total": 100}
        checker, config, _, _, _ = _make_checker(host_info=host_info)
        config.alert_conditions = [_cond(AlertType.DISK_USAGE, threshold_percent=85.0)]
        result = await checker.check_all()
        assert result[0].severity == "warning"

    async def test_disk_usage_below_threshold_no_alert(self):
        host_info = {"disk_used": 70, "disk_total": 100}
        checker, config, _, _, _ = _make_checker(host_info=host_info)
        config.alert_conditions = [_cond(AlertType.DISK_USAGE, threshold_percent=85.0)]
        result = await checker.check_all()
        assert result == []

    async def test_disk_usage_zero_total_no_alert(self):
        host_info = {"disk_used": 0, "disk_total": 0}
        checker, config, _, _, _ = _make_checker(host_info=host_info)
        config.alert_conditions = [_cond(AlertType.DISK_USAGE, threshold_percent=85.0)]
        result = await checker.check_all()
        assert result == []

    async def test_disk_usage_supervisor_error(self):
        checker, config, _, sup, _ = _make_checker()
        sup.get_host_info = AsyncMock(side_effect=Exception("supervisor unreachable"))
        config.alert_conditions = [_cond(AlertType.DISK_USAGE, threshold_percent=85.0)]
        result = await checker.check_all()
        assert result == []

    async def test_unknown_condition_type_ignored(self):
        checker, config, _, _, _ = _make_checker()
        cond = _cond("unknown_type")
        config.alert_conditions = [cond]
        result = await checker.check_all()
        assert result == []
