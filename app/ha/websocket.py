"""
Persistent WebSocket client for HA Core.

Protocol:
  connect → recv auth_required → send auth → recv auth_ok
  → send subscribe_events → recv result → recv event stream

Auto-reconnect: delays 5/10/30/60s on failure, then background retry every 60s.
Re-subscribes all event types after reconnect.
Circuit breaker integrated via DegradationMap.
"""
from __future__ import annotations

import asyncio
import json
from typing import Any, Callable, Coroutine, Optional, TYPE_CHECKING

import aiohttp

from app.observability.logger import get_logger

if TYPE_CHECKING:
    from app.core.degradation import DegradationMap

logger = get_logger(__name__)

WS_URL = "ws://supervisor/core/websocket"
RECONNECT_DELAYS = (5, 10, 30, 60)
BACKGROUND_RETRY_INTERVAL = 60


class WebSocketError(Exception):
    pass


class WebSocketAuthError(WebSocketError):
    pass


EventCallback = Callable[[dict[str, Any]], Coroutine]


class HAWebSocket:
    def __init__(
        self,
        supervisor_token: str,
        degradation: Optional["DegradationMap"] = None,
        ws_url: str = WS_URL,
    ) -> None:
        self._token = supervisor_token
        self._deg = degradation
        self._ws_url = ws_url
        self._session: Optional[aiohttp.ClientSession] = None
        self._ws: Optional[aiohttp.ClientWebSocketResponse] = None
        self._msg_id = 0
        # event_type -> list of async callbacks
        self._subscriptions: dict[str, list[EventCallback]] = {}
        # in-flight command id -> Future
        self._pending: dict[int, asyncio.Future] = {}
        self._connected = False
        self._listen_task: Optional[asyncio.Task] = None
        self._retry_task: Optional[asyncio.Task] = None

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #

    async def connect(self) -> None:
        """Open WS connection. Starts listen loop if successful."""
        self._session = aiohttp.ClientSession()
        success = await self._do_connect()
        if success:
            self._listen_task = asyncio.create_task(
                self._listen_loop(), name="ws_listen"
            )
        else:
            self._retry_task = asyncio.create_task(
                self._background_retry(), name="ws_retry"
            )

    async def disconnect(self) -> None:
        self._connected = False
        for task in (self._listen_task, self._retry_task):
            if task:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
        if self._ws and not self._ws.closed:
            await self._ws.close()
        if self._session:
            await self._session.close()
        logger.info("websocket_disconnected")

    async def subscribe_events(
        self,
        event_type: str,
        callback: EventCallback,
    ) -> None:
        """
        Subscribe to an HA event type. Callback is called with the full
        event dict for every matching event. If currently disconnected,
        the subscription is stored and re-applied after reconnect.
        """
        # Always store the callback for reconnect re-subscription
        if event_type not in self._subscriptions:
            self._subscriptions[event_type] = []
        self._subscriptions[event_type].append(callback)

        if self._connected and self._ws and not self._ws.closed:
            await self._send_subscribe(event_type)

    @property
    def is_connected(self) -> bool:
        return self._connected

    # ------------------------------------------------------------------ #
    # Connection internals
    # ------------------------------------------------------------------ #

    async def _do_connect(self) -> bool:
        """Attempt to open WS and complete HA auth handshake."""
        try:
            self._ws = await self._session.ws_connect(
                self._ws_url,
                heartbeat=30,
                timeout=aiohttp.ClientWSTimeout(ws_close=10),
            )
            # 1. Receive auth_required
            raw = await asyncio.wait_for(self._ws.receive(), timeout=10)
            msg = json.loads(raw.data)
            if msg.get("type") != "auth_required":
                raise WebSocketError(f"Expected auth_required, got: {msg.get('type')}")

            # 2. Send auth
            await self._ws.send_json(
                {"type": "auth", "access_token": self._token}
            )

            # 3. Receive auth result
            raw = await asyncio.wait_for(self._ws.receive(), timeout=10)
            result = json.loads(raw.data)
            if result.get("type") == "auth_invalid":
                raise WebSocketAuthError("WS auth invalid — check SUPERVISOR_TOKEN")
            if result.get("type") != "auth_ok":
                raise WebSocketError(f"Unexpected auth response: {result.get('type')}")

            self._connected = True
            if self._deg:
                self._deg.set_healthy("websocket")
            ha_version = result.get("ha_version", "unknown")
            logger.info("websocket_connected", ha_version=ha_version)

            # Re-subscribe all existing subscriptions (after reconnect)
            for event_type in list(self._subscriptions.keys()):
                await self._send_subscribe(event_type)

            return True

        except WebSocketAuthError:
            raise  # propagate — no point retrying auth errors
        except Exception as exc:
            self._connected = False
            if self._deg:
                self._deg.set_degraded("websocket", str(exc))
            logger.warning("websocket_connect_failed", error=str(exc))
            return False

    async def _send_subscribe(self, event_type: str) -> None:
        """Send subscribe_events command and wait for result confirmation."""
        msg_id = self._next_id()
        loop = asyncio.get_event_loop()
        fut: asyncio.Future = loop.create_future()
        self._pending[msg_id] = fut
        try:
            await self._ws.send_json(
                {"id": msg_id, "type": "subscribe_events", "event_type": event_type}
            )
            await asyncio.wait_for(asyncio.shield(fut), timeout=5)
            logger.debug("ws_subscribed", event_type=event_type)
        except asyncio.TimeoutError:
            logger.warning("ws_subscribe_timeout", event_type=event_type)
            self._pending.pop(msg_id, None)
        except Exception as exc:
            logger.error("ws_subscribe_error", event_type=event_type, error=str(exc))
            self._pending.pop(msg_id, None)

    # ------------------------------------------------------------------ #
    # Listen loop
    # ------------------------------------------------------------------ #

    async def _listen_loop(self) -> None:
        """Read messages from WS; reconnect on disconnect."""
        consecutive_failures = 0
        while True:
            try:
                if not self._ws or self._ws.closed:
                    await self._reconnect()
                    continue

                msg = await self._ws.receive()

                if msg.type in (aiohttp.WSMsgType.CLOSE, aiohttp.WSMsgType.CLOSED):
                    logger.warning("ws_closed_by_server")
                    consecutive_failures += 1
                    await self._reconnect()
                    continue

                if msg.type == aiohttp.WSMsgType.ERROR:
                    logger.warning("ws_message_error", error=str(msg.data))
                    await self._reconnect()
                    continue

                if msg.type != aiohttp.WSMsgType.TEXT:
                    continue

                consecutive_failures = 0
                data = json.loads(msg.data)
                await self._dispatch(data)

            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.error("ws_listen_error", error=str(exc))
                consecutive_failures += 1
                if consecutive_failures >= 3:
                    if self._deg:
                        self._deg.record_failure("websocket", str(exc))
                    logger.critical(
                        "ws_circuit_open", failures=consecutive_failures
                    )
                    # Switch to background retry mode
                    self._connected = False
                    asyncio.create_task(self._background_retry())
                    break
                await asyncio.sleep(5)

    async def _reconnect(self) -> None:
        """Try to reconnect with exponential backoff."""
        self._connected = False
        if self._deg:
            self._deg.set_degraded("websocket", "reconnecting")

        for delay in RECONNECT_DELAYS:
            logger.info("ws_reconnect_attempt", delay=delay)
            await asyncio.sleep(delay)
            success = await self._do_connect()
            if success:
                return

        # All reconnect attempts failed — switch to background retry
        logger.critical("ws_reconnect_exhausted")
        if self._deg:
            self._deg.record_failure("websocket", "reconnect exhausted")
        asyncio.create_task(self._background_retry())

    async def _background_retry(self) -> None:
        """Retry connection every 60s until successful."""
        while True:
            await asyncio.sleep(BACKGROUND_RETRY_INTERVAL)
            try:
                success = await self._do_connect()
                if success:
                    self._listen_task = asyncio.create_task(
                        self._listen_loop(), name="ws_listen"
                    )
                    return
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.warning("ws_background_retry_failed", error=str(exc))

    # ------------------------------------------------------------------ #
    # Message dispatch
    # ------------------------------------------------------------------ #

    async def _dispatch(self, data: dict[str, Any]) -> None:
        msg_type = data.get("type")

        if msg_type == "result":
            msg_id = data.get("id")
            fut = self._pending.pop(msg_id, None)
            if fut and not fut.done():
                if data.get("success"):
                    fut.set_result(data)
                else:
                    fut.set_exception(
                        WebSocketError(str(data.get("error", "command failed")))
                    )

        elif msg_type == "event":
            event = data.get("event", {})
            event_type = event.get("event_type", "")
            callbacks = self._subscriptions.get(event_type, [])
            for cb in callbacks:
                asyncio.create_task(cb(event))

        elif msg_type == "pong":
            pass  # heartbeat response

        else:
            logger.debug("ws_unknown_message_type", type=msg_type)

    async def send_command(self, command: dict) -> Any:
        """
        Send an arbitrary WS command and await the 'result' field.
        Raises WebSocketError if not connected or if the command fails.
        """
        if not self._connected or not self._ws or self._ws.closed:
            raise WebSocketError("WebSocket not connected")
        msg_id = self._next_id()
        payload = {**command, "id": msg_id}
        loop = asyncio.get_running_loop()
        fut: asyncio.Future = loop.create_future()
        self._pending[msg_id] = fut
        try:
            await self._ws.send_json(payload)
            result = await asyncio.wait_for(asyncio.shield(fut), timeout=10)
            return result.get("result")
        except asyncio.TimeoutError:
            self._pending.pop(msg_id, None)
            raise WebSocketError("WS command timed out")

    def _next_id(self) -> int:
        self._msg_id += 1
        return self._msg_id
