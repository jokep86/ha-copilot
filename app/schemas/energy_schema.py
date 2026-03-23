"""
Energy monitor schemas.
"""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class EnergyReading(BaseModel):
    entity_id: str
    friendly_name: Optional[str] = None
    state: float
    unit: str
    timestamp: str


class EnergyReport(BaseModel):
    period: str  # "today", "week", "month"
    start_time: str
    end_time: str
    readings: list[EnergyReading] = Field(default_factory=list)
    total_kwh: Optional[float] = None
    estimated_cost: Optional[float] = None


class AnomalyAlert(BaseModel):
    entity_id: str
    current_value: float
    rolling_average: float
    multiplier: float
    description: str
