"""
Lovelace dashboard schema.
"""
from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field


class LovelaceView(BaseModel):
    title: str
    path: Optional[str] = None
    cards: list[dict[str, Any]] = Field(default_factory=list)

    model_config = {"extra": "allow"}


class DashboardConfig(BaseModel):
    title: str
    views: list[LovelaceView] = Field(default_factory=list)

    model_config = {"extra": "allow"}
