"""
HA Core REST API client.
Single aiohttp.ClientSession for the add-on lifecycle (never create per-request).
Exponential backoff: 3 retries at 1s / 2s / 4s on all external calls.
"""
from __future__ import annotations

import asyncio
from typing import Any, Optional

import aiohttp

from app.observability.logger import get_logger

logger = get_logger(__name__)

HA_BASE_URL = "http://supervisor/core/api"
RETRY_DELAYS = (1, 2, 4)


class HAConnectionError(Exception):
    pass


class HAAuthError(Exception):
    pass


class ServiceCallError(Exception):
    pass


class HAClient:
    def __init__(
        self,
        supervisor_token: str,
        base_url: str = HA_BASE_URL,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self._token = supervisor_token
        self._session: Optional[aiohttp.ClientSession] = None

    async def connect(self) -> None:
        """Create the shared session. Call once at startup."""
        self._session = aiohttp.ClientSession(
            headers={
                "Authorization": f"Bearer {self._token}",
                "Content-Type": "application/json",
            },
            timeout=aiohttp.ClientTimeout(total=30),
        )
        logger.info("ha_client_connected", base_url=self.base_url)

    async def disconnect(self) -> None:
        if self._session:
            await self._session.close()
            self._session = None
            logger.info("ha_client_disconnected")

    @property
    def session(self) -> aiohttp.ClientSession:
        if not self._session:
            raise HAConnectionError("HAClient not connected — call connect() first")
        return self._session

    async def _request(
        self,
        method: str,
        path: str,
        json: Optional[dict] = None,
        params: Optional[dict] = None,
    ) -> Any:
        """HTTP request with exponential backoff. Raises domain-specific errors."""
        url = f"{self.base_url}{path}"
        last_exc: Optional[Exception] = None

        for attempt, delay in enumerate((*RETRY_DELAYS, None), start=1):
            try:
                async with self.session.request(
                    method, url, json=json, params=params
                ) as resp:
                    if resp.status == 401:
                        raise HAAuthError("HA API 401 — check SUPERVISOR_TOKEN")
                    if resp.status >= 500:
                        raise HAConnectionError(f"HA API server error {resp.status}")
                    resp.raise_for_status()
                    ct = resp.content_type or ""
                    if "json" in ct:
                        return await resp.json()
                    return await resp.text()
            except HAAuthError:
                raise  # Never retry auth errors
            except Exception as exc:
                last_exc = exc
                if delay is not None:
                    logger.warning(
                        "ha_api_retry",
                        attempt=attempt,
                        delay=delay,
                        path=path,
                        error=str(exc),
                    )
                    await asyncio.sleep(delay)

        raise HAConnectionError(
            f"HA API unreachable after {len(RETRY_DELAYS)} retries: {last_exc}"
        )

    # --- States ---

    async def get_states(self) -> list[dict]:
        return await self._request("GET", "/states")

    async def get_state(self, entity_id: str) -> dict:
        return await self._request("GET", f"/states/{entity_id}")

    # --- Services ---

    async def call_service(
        self,
        domain: str,
        service: str,
        service_data: Optional[dict] = None,
    ) -> Any:
        return await self._request(
            "POST",
            f"/services/{domain}/{service}",
            json=service_data or {},
        )

    # --- Config ---

    async def get_config(self) -> dict:
        return await self._request("GET", "/config")

    async def check_config(self) -> dict:
        return await self._request("POST", "/config/core/check")

    # --- History ---

    async def get_history(self, entity_id: str, hours: int = 24) -> list:
        from datetime import datetime, timedelta, timezone

        start = (
            datetime.now(timezone.utc) - timedelta(hours=hours)
        ).isoformat()
        return await self._request(
            "GET",
            f"/history/period/{start}",
            params={"filter_entity_id": entity_id},
        )

    # --- Templates ---

    async def render_template(self, template: str) -> str:
        result = await self._request("POST", "/template", json={"template": template})
        return str(result)

    # --- Automations (Config API) ---

    async def get_automations(self) -> list[dict]:
        return await self._request("GET", "/config/automation/config")

    async def create_automation(self, config: dict) -> dict:
        return await self._request("POST", "/config/automation/config", json=config)

    async def update_automation(self, automation_id: str, config: dict) -> dict:
        return await self._request(
            "PUT", f"/config/automation/config/{automation_id}", json=config
        )

    async def delete_automation(self, automation_id: str) -> None:
        await self._request("DELETE", f"/config/automation/config/{automation_id}")

    # --- Scenes (Config API) ---

    async def get_scenes(self) -> list[dict]:
        return await self._request("GET", "/config/scene/config")

    async def create_scene(self, config: dict) -> dict:
        return await self._request("POST", "/config/scene/config", json=config)

    async def delete_scene(self, scene_id: str) -> None:
        await self._request("DELETE", f"/config/scene/config/{scene_id}")
