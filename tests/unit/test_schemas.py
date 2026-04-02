"""
Unit tests for Pydantic schemas.
Validates that schema models accept valid data and reject invalid data.
"""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.schemas.ai_action import AIAction, AIResponse, ActionType
from app.schemas.alert_config import AlertCondition, AlertEvent, AlertType, AutoFixLevel
from app.schemas.automation_schema import AutomationConfig
from app.schemas.device_command import DeviceCommand, DeviceState
from app.schemas.energy_schema import AnomalyAlert, EnergyReport
from app.schemas.scene_schema import SceneConfig
from app.schemas.snapshot_schema import EntitySnapshot, SnapshotDiff
from app.schemas.system_query import AddonInfo, SystemInfo, SystemMetrics


# --- AIAction ---

def test_ai_action_minimal() -> None:
    action = AIAction(action_type=ActionType.CALL_SERVICE)
    assert action.action_type == ActionType.CALL_SERVICE
    assert action.confidence == 1.0
    assert action.entity_ids == []


def test_ai_action_full() -> None:
    action = AIAction(
        action_type=ActionType.CALL_SERVICE,
        domain="light",
        service="turn_on",
        entity_id="light.sala",
        service_data={"brightness": 128},
        confidence=0.95,
    )
    assert action.domain == "light"
    assert action.service_data["brightness"] == 128


def test_ai_action_confidence_bounds() -> None:
    with pytest.raises(ValidationError):
        AIAction(action_type=ActionType.UNKNOWN, confidence=1.5)
    with pytest.raises(ValidationError):
        AIAction(action_type=ActionType.UNKNOWN, confidence=-0.1)


# --- AIResponse ---

def test_ai_response_valid() -> None:
    resp = AIResponse(
        actions=[AIAction(action_type=ActionType.GET_STATE)],
        raw_response="{}",
        prompt_version="v1",
        model="claude-sonnet-4-20250514",
        input_tokens=100,
        output_tokens=50,
        trace_id="abc-123",
    )
    assert len(resp.actions) == 1
    assert resp.from_cache is False


# --- DeviceCommand ---

def test_device_command_valid() -> None:
    cmd = DeviceCommand(
        entity_id="light.sala",
        domain="light",
        service="turn_on",
        trace_id="trace-1",
    )
    assert cmd.domain == "light"


# --- DeviceState ---

def test_device_state_domain_property() -> None:
    state = DeviceState(entity_id="light.sala", state="on")
    assert state.domain == "light"


def test_device_state_friendly_name_fallback() -> None:
    state = DeviceState(entity_id="light.sala", state="on")
    assert state.friendly_name == "light.sala"


def test_device_state_friendly_name_from_attrs() -> None:
    state = DeviceState(
        entity_id="light.sala",
        state="on",
        attributes={"friendly_name": "Sala Light"},
    )
    assert state.friendly_name == "Sala Light"


# --- AutomationConfig ---

def test_automation_config_valid() -> None:
    auto = AutomationConfig(
        alias="Test Automation",
        trigger=[{"platform": "state", "entity_id": "binary_sensor.door"}],
        action=[{"service": "light.turn_on", "target": {"entity_id": "light.sala"}}],
    )
    assert auto.alias == "Test Automation"
    assert auto.mode == "single"
    assert auto.condition == []


def test_automation_config_requires_alias() -> None:
    with pytest.raises(ValidationError):
        AutomationConfig(
            trigger=[{"platform": "state"}],
            action=[{"service": "light.turn_on"}],
        )


# --- SceneConfig ---

def test_scene_config_valid() -> None:
    scene = SceneConfig(
        name="Evening",
        entities={"light.sala": {"state": "on", "brightness": 100}},
    )
    assert scene.name == "Evening"


# --- AlertCondition ---

def test_alert_condition_defaults() -> None:
    cond = AlertCondition(type="low_battery")
    assert cond.enabled is True
    assert cond.cooldown_seconds == 300


# --- AlertEvent ---

def test_alert_event_risk_score_bounds() -> None:
    with pytest.raises(ValidationError):
        AlertEvent(
            alert_type=AlertType.LOW_BATTERY,
            severity="warning",
            description="Battery low",
            risk_score=6,  # > 5
        )


def test_alert_event_valid() -> None:
    event = AlertEvent(
        alert_type=AlertType.DEVICE_UNAVAILABLE,
        severity="critical",
        entity_id="sensor.door",
        description="Device unavailable",
        risk_score=2,
    )
    assert event.risk_score == 2


# --- AutoFixLevel ---

def test_auto_fix_level_values() -> None:
    assert AutoFixLevel.TRIVIAL == 1
    assert AutoFixLevel.CRITICAL == 5


# --- EnergyReport ---

def test_energy_report_empty() -> None:
    report = EnergyReport(
        period="today",
        start_time="2026-03-23T00:00:00Z",
        end_time="2026-03-23T23:59:59Z",
    )
    assert report.readings == []
    assert report.total_kwh is None


# --- EntitySnapshot ---

def test_entity_snapshot_valid() -> None:
    snap = EntitySnapshot(
        name="before_update",
        timestamp="2026-03-23T10:00:00Z",
        user_id=111111,
        states={"light.sala": {"state": "on"}},
        entity_count=1,
    )
    assert snap.entity_count == 1


# --- SnapshotDiff ---

def test_snapshot_diff_defaults() -> None:
    diff = SnapshotDiff(
        snapshot_name="before_update",
        snapshot_timestamp="2026-03-23T10:00:00Z",
        current_timestamp="2026-03-23T11:00:00Z",
    )
    assert diff.added == []
    assert diff.removed == []
    assert diff.changed == {}


# --- SystemInfo ---

def test_system_info_defaults() -> None:
    info = SystemInfo()
    assert info.ha_version is None
    assert info.addons == []
    assert info.metrics.cpu_percent is None


# --- DashboardSchema ---

def test_lovelace_view_defaults() -> None:
    from app.schemas.dashboard_schema import LovelaceView
    view = LovelaceView(title="Living Room")
    assert view.title == "Living Room"
    assert view.path is None
    assert view.cards == []


def test_lovelace_view_with_cards() -> None:
    from app.schemas.dashboard_schema import LovelaceView
    view = LovelaceView(title="Test", path="test", cards=[{"type": "entity"}])
    assert view.path == "test"
    assert len(view.cards) == 1


def test_dashboard_config_defaults() -> None:
    from app.schemas.dashboard_schema import DashboardConfig
    cfg = DashboardConfig(title="My Dashboard")
    assert cfg.title == "My Dashboard"
    assert cfg.views == []


def test_dashboard_config_with_views() -> None:
    from app.schemas.dashboard_schema import DashboardConfig, LovelaceView
    cfg = DashboardConfig(
        title="Home",
        views=[LovelaceView(title="Main"), LovelaceView(title="Energy")],
    )
    assert len(cfg.views) == 2


# --- EventSubscription ---

def test_event_subscription_defaults() -> None:
    from app.schemas.event_subscription import EventSubscription
    sub = EventSubscription(event_type="state_changed")
    assert sub.event_type == "state_changed"
    assert sub.domain_filter == []
    assert sub.entity_pattern is None
    assert sub.cooldown_seconds == 60
    assert sub.enabled is True


def test_event_subscription_full() -> None:
    from app.schemas.event_subscription import EventSubscription
    sub = EventSubscription(
        event_type="automation_triggered",
        domain_filter=["light", "switch"],
        entity_pattern="light.*",
        cooldown_seconds=300,
        enabled=False,
    )
    assert sub.domain_filter == ["light", "switch"]
    assert sub.cooldown_seconds == 300
    assert sub.enabled is False
