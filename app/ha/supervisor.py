"""
Supervisor API client.
$SUPERVISOR_TOKEN is auto-injected by Supervisor — never store or log it.
Exponential backoff: 3 retries at 1s / 2s / 4s.
"""
from __future__ import annotations

import asyncio
from typing import Any, Optional

import aiohttp

from app.observability.logger import get_logger

logger = get_logger(__name__)

SUPERVISOR_BASE_URL = "http://supervisor"
RETRY_DELAYS = (1, 2, 4)


class SupervisorConnectionError(Exception):
    pass


class SupervisorClient:
    def __init__(
        self,
        supervisor_token: str,
        base_url: str = SUPERVISOR_BASE_URL,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self._token = supervisor_token
        self._session: Optional[aiohttp.ClientSession] = None

    async def connect(self) -> None:
        self._session = aiohttp.ClientSession(
            headers={
                "Authorization": f"Bearer {self._token}",
                "Content-Type": "application/json",
            },
            timeout=aiohttp.ClientTimeout(total=30),
        )
        logger.info("supervisor_client_connected")

    async def disconnect(self) -> None:
        if self._session:
            await self._session.close()
            self._session = None
            logger.info("supervisor_client_disconnected")

    @property
    def session(self) -> aiohttp.ClientSession:
        if not self._session:
            raise SupervisorConnectionError(
                "SupervisorClient not connected — call connect() first"
            )
        return self._session

    async def _request(
        self,
        method: str,
        path: str,
        json: Optional[dict] = None,
    ) -> Any:
        url = f"{self.base_url}{path}"
        last_exc: Optional[Exception] = None

        for attempt, delay in enumerate((*RETRY_DELAYS, None), start=1):
            try:
                async with self.session.request(method, url, json=json) as resp:
                    if resp.status >= 500:
                        raise SupervisorConnectionError(
                            f"Supervisor error {resp.status}"
                        )
                    resp.raise_for_status()
                    data = await resp.json()
                    # Supervisor wraps: {"result": "ok", "data": {...}}
                    return data.get("data", data)
            except Exception as exc:
                last_exc = exc
                if delay is not None:
                    logger.warning(
                        "supervisor_api_retry",
                        attempt=attempt,
                        delay=delay,
                        path=path,
                        error=str(exc),
                    )
                    await asyncio.sleep(delay)

        raise SupervisorConnectionError(
            f"Supervisor API unreachable after {len(RETRY_DELAYS)} retries: {last_exc}"
        )

    async def get_info(self) -> dict:
        return await self._request("GET", "/supervisor/info")

    async def get_host_info(self) -> dict:
        return await self._request("GET", "/host/info")

    async def get_os_info(self) -> dict:
        return await self._request("GET", "/os/info")

    async def get_core_info(self) -> dict:
        return await self._request("GET", "/core/info")

    async def get_addons(self) -> list[dict]:
        data = await self._request("GET", "/addons")
        return data.get("addons", []) if isinstance(data, dict) else []

    async def get_addon_info(self, slug: str) -> dict:
        return await self._request("GET", f"/addons/{slug}/info")

    async def restart_addon(self, slug: str) -> None:
        await self._request("POST", f"/addons/{slug}/restart")

    async def restart_core(self) -> None:
        await self._request("POST", "/core/restart")

    async def reboot_host(self) -> None:
        await self._request("POST", "/host/reboot")

    async def get_backups(self) -> list[dict]:
        data = await self._request("GET", "/backups")
        return data.get("backups", []) if isinstance(data, dict) else []

    async def create_backup(self) -> dict:
        return await self._request("POST", "/backups/new/full")

    async def get_logs(self, source: str = "core") -> str:
        """Get logs as plain text. source: core, supervisor, host, or an add-on slug."""
        if source in ("core", "supervisor", "host"):
            path = f"/{source}/logs"
        else:
            path = f"/addons/{source}/logs"
        return await self._request_text("GET", path)

    async def _request_text(self, method: str, path: str) -> str:
        """Like _request but returns raw text (for log endpoints)."""
        url = f"{self.base_url}{path}"
        last_exc: Exception | None = None
        for attempt, delay in enumerate((*RETRY_DELAYS, None), start=1):
            try:
                async with self.session.request(method, url) as resp:
                    resp.raise_for_status()
                    return await resp.text()
            except Exception as exc:
                last_exc = exc
                if delay is not None:
                    logger.warning(
                        "supervisor_api_text_retry",
                        attempt=attempt,
                        delay=delay,
                        path=path,
                        error=str(exc),
                    )
                    await asyncio.sleep(delay)
        raise SupervisorConnectionError(
            f"Supervisor API unreachable after {len(RETRY_DELAYS)} retries: {last_exc}"
        )
