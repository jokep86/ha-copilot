"""
Entity snapshot and diff schemas.
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class EntitySnapshot(BaseModel):
    name: str
    timestamp: str
    user_id: int
    states: dict[str, Any]  # entity_id -> full state dict
    entity_count: int


class SnapshotDiff(BaseModel):
    snapshot_name: str
    snapshot_timestamp: str
    current_timestamp: str
    added: list[str] = Field(default_factory=list)    # new entity_ids
    removed: list[str] = Field(default_factory=list)  # gone entity_ids
    changed: dict[str, tuple[str, str]] = Field(default_factory=dict)  # id -> (old, new)
    unchanged_count: int = 0
