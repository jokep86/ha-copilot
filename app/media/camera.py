"""
Camera snapshot handler.
Fetches camera images from HA's camera proxy endpoint.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.ha.client import HAClient


class CameraError(Exception):
    pass


async def fetch_snapshot(ha_client: "HAClient", entity_id: str) -> bytes:
    """
    Fetch a camera snapshot from HA.
    Returns raw image bytes (JPEG or PNG).
    Raises CameraError on failure.
    """
    try:
        data = await ha_client.get_camera_image(entity_id)
        if not data:
            raise CameraError(f"Empty response for camera entity '{entity_id}'")
        return data
    except CameraError:
        raise
    except Exception as exc:
        raise CameraError(f"Failed to fetch camera snapshot: {exc}") from exc
