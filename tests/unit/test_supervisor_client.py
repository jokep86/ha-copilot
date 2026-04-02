"""
Unit tests for SupervisorClient.
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from app.ha.supervisor import SupervisorClient, SupervisorConnectionError


def _make_client():
    return SupervisorClient(supervisor_token="test_token")


def _wrapped_response(data):
    """Supervisor API wraps responses as {"result": "ok", "data": {...}}."""
    return {"result": "ok", "data": data}


def _make_response(status=200, json_data=None, text_data=None):
    resp = MagicMock()
    resp.status = status
    resp.json = AsyncMock(return_value=json_data or {})
    resp.text = AsyncMock(return_value=text_data or "")
    resp.raise_for_status = MagicMock()
    return resp


def _mock_session(response):
    session = MagicMock()

    @asynccontextmanager
    async def _request(*args, **kwargs):
        yield response

    session.request = _request
    return session


class TestSupervisorClientLifecycle:
    async def test_connect_creates_session(self):
        client = _make_client()
        await client.connect()
        assert client._session is not None
        await client.disconnect()

    async def test_disconnect_closes_session(self):
        client = _make_client()
        await client.connect()
        await client.disconnect()
        assert client._session is None

    async def test_disconnect_without_connect_is_noop(self):
        client = _make_client()
        await client.disconnect()

    async def test_session_raises_when_not_connected(self):
        client = _make_client()
        with pytest.raises(SupervisorConnectionError):
            _ = client.session

    async def test_base_url_trailing_slash_stripped(self):
        client = SupervisorClient("token", base_url="http://supervisor/")
        assert client.base_url == "http://supervisor"


class TestSupervisorClientRequests:
    async def test_get_info(self):
        client = _make_client()
        resp = _make_response(200, _wrapped_response({"version": "2025.1.0"}))
        client._session = _mock_session(resp)
        result = await client.get_info()
        assert result == {"version": "2025.1.0"}

    async def test_get_host_info(self):
        client = _make_client()
        resp = _make_response(200, _wrapped_response({"disk_used": 10, "disk_total": 100}))
        client._session = _mock_session(resp)
        result = await client.get_host_info()
        assert result["disk_total"] == 100

    async def test_get_core_info(self):
        client = _make_client()
        resp = _make_response(200, _wrapped_response({"version": "2026.3.0"}))
        client._session = _mock_session(resp)
        result = await client.get_core_info()
        assert result["version"] == "2026.3.0"

    async def test_get_os_info(self):
        client = _make_client()
        resp = _make_response(200, _wrapped_response({"version": "14.0"}))
        client._session = _mock_session(resp)
        result = await client.get_os_info()
        assert result["version"] == "14.0"

    async def test_get_addons_returns_list(self):
        client = _make_client()
        resp = _make_response(200, _wrapped_response({
            "addons": [{"slug": "mqtt", "name": "MQTT", "state": "started"}]
        }))
        client._session = _mock_session(resp)
        result = await client.get_addons()
        assert len(result) == 1
        assert result[0]["slug"] == "mqtt"

    async def test_get_addons_non_dict_returns_empty(self):
        client = _make_client()
        resp = _make_response(200, json_data=[])  # Not wrapped
        client._session = _mock_session(resp)
        result = await client.get_addons()
        assert result == []

    async def test_get_addon_info(self):
        client = _make_client()
        resp = _make_response(200, _wrapped_response({"slug": "mqtt", "state": "started"}))
        client._session = _mock_session(resp)
        result = await client.get_addon_info("mqtt")
        assert result["slug"] == "mqtt"

    async def test_restart_addon(self):
        client = _make_client()
        resp = _make_response(200, _wrapped_response({}))
        client._session = _mock_session(resp)
        await client.restart_addon("mqtt")

    async def test_restart_core(self):
        client = _make_client()
        resp = _make_response(200, _wrapped_response({}))
        client._session = _mock_session(resp)
        await client.restart_core()

    async def test_reboot_host(self):
        client = _make_client()
        resp = _make_response(200, _wrapped_response({}))
        client._session = _mock_session(resp)
        await client.reboot_host()

    async def test_get_backups_returns_list(self):
        client = _make_client()
        resp = _make_response(200, _wrapped_response({
            "backups": [{"slug": "abc123", "name": "Full backup"}]
        }))
        client._session = _mock_session(resp)
        result = await client.get_backups()
        assert len(result) == 1

    async def test_create_backup(self):
        client = _make_client()
        resp = _make_response(200, _wrapped_response({"slug": "new_backup"}))
        client._session = _mock_session(resp)
        result = await client.create_backup()
        assert result == {"slug": "new_backup"}

    async def test_get_logs_core(self):
        client = _make_client()
        resp = _make_response(200, text_data="[2026-01-01] INFO core started")
        client._session = _mock_session(resp)
        result = await client.get_logs("core")
        assert "core started" in result

    async def test_get_logs_addon_slug(self):
        client = _make_client()
        resp = _make_response(200, text_data="[INFO] mqtt started")
        client._session = _mock_session(resp)
        result = await client.get_logs("mqtt")
        assert "mqtt started" in result


class TestSupervisorClientErrors:
    async def test_connection_error_on_500(self):
        client = _make_client()
        resp = _make_response(500)
        client._session = _mock_session(resp)
        with patch("app.ha.supervisor.asyncio.sleep", AsyncMock()):
            with pytest.raises(SupervisorConnectionError):
                await client.get_info()

    async def test_retries_on_network_error(self):
        client = _make_client()
        call_count = 0

        session = MagicMock()

        @asynccontextmanager
        async def _failing(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            raise Exception("connection refused")
            yield

        session.request = _failing
        client._session = session

        with patch("app.ha.supervisor.asyncio.sleep", AsyncMock()):
            with pytest.raises(SupervisorConnectionError):
                await client.get_info()

        assert call_count == 4  # 3 retries + final
