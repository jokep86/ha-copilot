"""
Device command and state schemas.
"""
from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field


class DeviceCommand(BaseModel):
    entity_id: str
    domain: str
    service: str
    service_data: dict[str, Any] = Field(default_factory=dict)
    trace_id: str


class DeviceState(BaseModel):
    entity_id: str
    state: str
    attributes: dict[str, Any] = Field(default_factory=dict)
    last_changed: Optional[str] = None
    last_updated: Optional[str] = None

    @property
    def domain(self) -> str:
        return self.entity_id.split(".")[0]

    @property
    def friendly_name(self) -> str:
        return self.attributes.get("friendly_name", self.entity_id)
