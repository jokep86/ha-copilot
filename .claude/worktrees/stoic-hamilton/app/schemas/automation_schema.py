"""
Automation config schema.
Phase 1 scope: simple automations (1 trigger, 1 action, no choose/repeat/parallel).
"""
from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field


class AutomationConfig(BaseModel):
    """Validated automation config before sending to HA."""

    alias: str
    description: Optional[str] = None
    mode: str = "single"
    trigger: list[dict[str, Any]]
    condition: list[dict[str, Any]] = Field(default_factory=list)
    action: list[dict[str, Any]]
    id: Optional[str] = None

    model_config = {"extra": "allow"}
