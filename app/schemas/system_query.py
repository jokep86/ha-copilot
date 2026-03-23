"""
System info and metrics schemas.
"""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel


class SystemMetrics(BaseModel):
    cpu_percent: Optional[float] = None
    memory_used_mb: Optional[float] = None
    memory_total_mb: Optional[float] = None
    disk_used_gb: Optional[float] = None
    disk_total_gb: Optional[float] = None
    uptime_seconds: Optional[int] = None


class AddonInfo(BaseModel):
    slug: str
    name: str
    state: str
    version: Optional[str] = None
    version_latest: Optional[str] = None
    update_available: bool = False


class SystemInfo(BaseModel):
    ha_version: Optional[str] = None
    supervisor_version: Optional[str] = None
    addon_version: Optional[str] = None
    metrics: SystemMetrics = SystemMetrics()
    addons: list[AddonInfo] = []
