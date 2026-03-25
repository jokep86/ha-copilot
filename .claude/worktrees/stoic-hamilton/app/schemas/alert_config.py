"""
Alert condition and auto-fix schemas.
Risk scoring: 1 (trivial) → 5 (critical). See ADR-007.
"""
from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class AlertType(str, Enum):
    DEVICE_UNAVAILABLE = "device_unavailable"
    LOW_BATTERY = "low_battery"
    DISK_USAGE = "disk_usage"
    INTEGRATION_ERROR = "integration_error"
    AUTOMATION_FAILED = "automation_failed"
    CRITICAL_LOG = "critical_log"


class AutoFixLevel(int, Enum):
    TRIVIAL = 1   # restart crashed add-on, clear temp files
    LOW = 2       # reload integration, clear cache
    MEDIUM = 3    # reinstall add-on, revert single config change
    HIGH = 4      # restart HA Core
    CRITICAL = 5  # restore backup, host reboot


class AlertCondition(BaseModel):
    type: str
    enabled: bool = True
    cooldown_seconds: int = 300
    threshold: Optional[float] = None
    threshold_percent: Optional[float] = None


class AlertEvent(BaseModel):
    alert_type: AlertType
    severity: str  # "info", "warning", "critical"
    entity_id: Optional[str] = None
    description: str
    risk_score: int = Field(ge=0, le=5, default=0)
    auto_fix_action: Optional[str] = None
