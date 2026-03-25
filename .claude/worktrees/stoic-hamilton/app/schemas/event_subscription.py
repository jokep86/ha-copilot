"""
Event subscription config schema.
"""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class EventSubscription(BaseModel):
    event_type: str
    domain_filter: list[str] = Field(default_factory=list)
    entity_pattern: Optional[str] = None
    cooldown_seconds: int = 60
    enabled: bool = True
