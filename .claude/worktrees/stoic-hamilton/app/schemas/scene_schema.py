"""
Scene config schema.
"""
from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field


class SceneConfig(BaseModel):
    name: str
    entities: dict[str, Any] = Field(default_factory=dict)
    id: Optional[str] = None

    model_config = {"extra": "allow"}
