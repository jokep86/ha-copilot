"""
Persistent WebSocket client for HA Core.
Phase 1: connection stub — proactive notifications and entity cache
invalidation are implemented in Phase 2.
"""
from __future__ import annotations

import asyncio
from typing import Any, Callable, Optional

from app.observability.logger import get_logger

logger = get_logger(__name__)

WS_URL = "ws://supervisor/core/websocket"

# Phase 2: reconnect delays
RECONNECT_DELAYS = (5, 10, 30, 60)


class WebSocketError(Exception):
    pass


class HAWebSocket:
    """
    Persistent WS client stub.
    Full implementation (auto-reconnect, entity cache invalidation,
    event subscriptions) ships in Phase 2.
    """

    def __init__(self, supervisor_token: str, ws_url: str = WS_URL) -> None:
        self._token = supervisor_token
        self._ws_url = ws_url
        self._connected = False
        self._subscriptions: dict[str, list[Callable[[dict], Any]]] = {}
        self._task: Optional[asyncio.Task] = None

    async def connect(self) -> None:
        """
        Phase 1: log intent, mark for Phase 2 implementation.
        The websocket state is set optimistically by self_test.
        """
        logger.info(
            "websocket_connect_stub",
            note="full_persistent_connection_in_phase2",
        )
        self._connected = False

    async def disconnect(self) -> None:
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        self._connected = False

    async def subscribe(
        self,
        event_type: str,
        callback: Callable[[dict], Any],
    ) -> None:
        """Register a callback for an event type (Phase 2: actually subscribes via WS)."""
        if event_type not in self._subscriptions:
            self._subscriptions[event_type] = []
        self._subscriptions[event_type].append(callback)
        logger.debug("websocket_subscribe_registered", event_type=event_type)

    @property
    def is_connected(self) -> bool:
        return self._connected
