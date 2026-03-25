"""
YAML/JSON file export for Telegram.
Serializes automations, scenes, or configuration.yaml for download.
"""
from __future__ import annotations

import io
import json
from pathlib import Path
from typing import TYPE_CHECKING

from ruamel.yaml import YAML

from app.observability.logger import get_logger

if TYPE_CHECKING:
    from app.ha.client import HAClient

logger = get_logger(__name__)

_yaml = YAML()
_yaml.default_flow_style = False

_CONFIG_FILE = Path("/homeassistant/configuration.yaml")


class ExportError(Exception):
    pass


async def export_automations(ha_client: "HAClient") -> tuple[bytes, str]:
    """
    Returns (yaml_bytes, filename) for all automations.
    """
    try:
        automations = await ha_client.get_automations()
    except Exception as exc:
        raise ExportError(f"Failed to fetch automations: {exc}") from exc

    buf = io.BytesIO()
    _yaml.dump(automations, buf)
    return buf.getvalue(), "automations.yaml"


async def export_scenes(ha_client: "HAClient") -> tuple[bytes, str]:
    """
    Returns (yaml_bytes, filename) for all scenes.
    """
    try:
        scenes = await ha_client.get_scenes()
    except Exception as exc:
        raise ExportError(f"Failed to fetch scenes: {exc}") from exc

    buf = io.BytesIO()
    _yaml.dump(scenes, buf)
    return buf.getvalue(), "scenes.yaml"


def export_config() -> tuple[bytes, str]:
    """
    Returns (yaml_bytes, filename) for configuration.yaml from disk.
    """
    if not _CONFIG_FILE.exists():
        raise ExportError(f"Config file not found: {_CONFIG_FILE}")
    try:
        content = _CONFIG_FILE.read_bytes()
        return content, "configuration.yaml"
    except OSError as exc:
        raise ExportError(f"Cannot read config file: {exc}") from exc


async def export_audit_log(db, days: int = 30) -> tuple[bytes, str]:
    """
    Returns (json_bytes, filename) for the AI audit log.
    """
    try:
        cursor = await db.conn.execute(
            "SELECT * FROM ai_audit_log "
            "WHERE timestamp > datetime('now', ?) "
            "ORDER BY timestamp DESC",
            (f"-{days} days",),
        )
        rows = await cursor.fetchall()
        data = [dict(r) for r in rows]
        content = json.dumps(data, indent=2, default=str).encode()
        return content, f"audit_log_{days}d.json"
    except Exception as exc:
        raise ExportError(f"Failed to export audit log: {exc}") from exc
