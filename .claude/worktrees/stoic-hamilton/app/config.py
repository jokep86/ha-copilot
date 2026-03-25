"""
Settings loader from /data/options.json (provided by HA Supervisor).
Override path via HA_OPTIONS_PATH env var for local development.
"""
from __future__ import annotations

import os
from typing import Any, Optional

import orjson
from pydantic import BaseModel, Field

OPTIONS_PATH = os.environ.get("HA_OPTIONS_PATH", "/data/options.json")


class AlertConditionConfig(BaseModel):
    type: str
    enabled: bool = True
    cooldown_seconds: Optional[int] = None
    threshold: Optional[float] = None
    threshold_percent: Optional[float] = None


class QuickActionStep(BaseModel):
    service: str
    target: dict[str, Any] = Field(default_factory=dict)


class QuickActionConfig(BaseModel):
    name: str
    actions: list[QuickActionStep]


class ConfirmationLevelsConfig(BaseModel):
    none: list[str] = Field(default_factory=list)
    single_click: list[str] = Field(default_factory=list)
    double_confirm: list[str] = Field(default_factory=list)
    password: list[str] = Field(default_factory=list)


class AppConfig(BaseModel):
    # --- Telegram ---
    telegram_bot_token: str
    allowed_telegram_ids: list[int]
    chat_mode: str = "both"
    telegram_mode: str = "polling"
    allowed_group_ids: list[int] = Field(default_factory=list)
    notification_target: str = "private"

    # --- AI ---
    anthropic_api_key: str
    ai_enabled: bool = True
    ai_model: str = "claude-sonnet-4-20250514"
    ai_max_tokens: int = 1024
    ai_daily_token_budget: int = 500000
    ai_conversation_memory: bool = True
    ai_conversation_ttl_minutes: int = 30
    ai_conversation_max_messages: int = 10

    # --- System ---
    log_level: str = "info"
    health_pulse_interval_seconds: int = 300
    dead_man_switch_timeout_seconds: int = 600
    health_check_interval_seconds: int = 300
    daily_digest_enabled: bool = True
    daily_digest_time: str = "08:00"
    db_purge_days: int = 90

    # --- Alerts ---
    alert_conditions: list[AlertConditionConfig] = Field(default_factory=list)
    auto_fix_max_risk_score: int = 1

    # --- Notifications ---
    proactive_notifications: bool = True
    notification_events: list[str] = Field(
        default_factory=lambda: ["state_changed", "automation_triggered"]
    )
    notification_domains: list[str] = Field(
        default_factory=lambda: ["binary_sensor", "alarm_control_panel"]
    )
    notification_entity_patterns: list[str] = Field(default_factory=list)

    # --- Entity Aliases ---
    entity_aliases: dict[str, str] = Field(default_factory=dict)

    # --- Quick Actions ---
    quick_actions: list[QuickActionConfig] = Field(default_factory=list)

    # --- Confirmation Levels ---
    confirmation_levels: ConfirmationLevelsConfig = Field(
        default_factory=ConfirmationLevelsConfig
    )


def load_config() -> AppConfig:
    """Load and validate configuration from /data/options.json."""
    with open(OPTIONS_PATH, "rb") as f:
        data = orjson.loads(f.read())
    return AppConfig.model_validate(data)
