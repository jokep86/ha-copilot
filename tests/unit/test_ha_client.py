"""
Unit tests for HAClient.
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from app.ha.client import HAClient, HAConnectionError, HAAuthError


def _make_client(base_url="http://supervisor/core/api"):
    return HAClient(supervisor_token="test_token", base_url=base_url)


def _make_response(status=200, json_data=None, text_data=None, content_type="application/json"):
    resp = MagicMock()
    resp.status = status
    resp.content_type = content_type
    if json_data is not None:
        resp.json = AsyncMock(return_value=json_data)
    if text_data is not None:
        resp.text = AsyncMock(return_value=text_data)
    resp.read = AsyncMock(return_value=b"image_bytes")
    resp.raise_for_status = MagicMock()
    return resp


def _mock_session(response):
    session = MagicMock()

    @asynccontextmanager
    async def _request(*args, **kwargs):
        yield response

    @asynccontextmanager
    async def _get(*args, **kwargs):
        yield response

    session.request = _request
    session.get = _get
    return session


class TestHAClientLifecycle:
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
        await client.disconnect()  # Should not raise

    async def test_session_raises_when_not_connected(self):
        client = _make_client()
        with pytest.raises(HAConnectionError):
            _ = client.session

    async def test_base_url_trailing_slash_stripped(self):
        client = HAClient("token", base_url="http://test/api/")
        assert client.base_url == "http://test/api"


class TestHAClientRequests:
    async def test_get_states_returns_list(self):
        client = _make_client()
        states = [{"entity_id": "light.sala", "state": "on"}]
        resp = _make_response(200, json_data=states)
        client._session = _mock_session(resp)
        result = await client.get_states()
        assert result == states

    async def test_get_state_single_entity(self):
        client = _make_client()
        state = {"entity_id": "light.sala", "state": "on"}
        resp = _make_response(200, json_data=state)
        client._session = _mock_session(resp)
        result = await client.get_state("light.sala")
        assert result == state

    async def test_call_service_success(self):
        client = _make_client()
        resp = _make_response(200, json_data=[])
        client._session = _mock_session(resp)
        await client.call_service("light", "turn_on", {"entity_id": "light.sala"})

    async def test_get_config_returns_dict(self):
        client = _make_client()
        resp = _make_response(200, json_data={"unit_system": {"length": "km"}})
        client._session = _mock_session(resp)
        result = await client.get_config()
        assert "unit_system" in result

    async def test_render_template_returns_string(self):
        client = _make_client()
        resp = _make_response(200, text_data="22.5", content_type="text/plain")
        client._session = _mock_session(resp)
        result = await client.render_template("{{ states('sensor.temp') }}")
        assert result == "22.5"

    async def test_get_automations_returns_list(self):
        client = _make_client()
        autos = [{"id": "abc", "alias": "Test"}]
        resp = _make_response(200, json_data=autos)
        client._session = _mock_session(resp)
        result = await client.get_automations()
        assert result == autos

    async def test_create_automation(self):
        client = _make_client()
        resp = _make_response(200, json_data={"id": "new123"})
        client._session = _mock_session(resp)
        result = await client.create_automation({"alias": "Test"})
        assert result == {"id": "new123"}

    async def test_delete_automation(self):
        client = _make_client()
        resp = _make_response(200, text_data="", content_type="text/plain")
        client._session = _mock_session(resp)
        await client.delete_automation("abc123")

    async def test_get_scenes_returns_list(self):
        client = _make_client()
        resp = _make_response(200, json_data=[{"id": "morning", "name": "Morning"}])
        client._session = _mock_session(resp)
        result = await client.get_scenes()
        assert len(result) == 1

    async def test_create_scene(self):
        client = _make_client()
        resp = _make_response(200, json_data={"id": "scene1"})
        client._session = _mock_session(resp)
        result = await client.create_scene({"name": "Morning"})
        assert result == {"id": "scene1"}

    async def test_delete_scene(self):
        client = _make_client()
        resp = _make_response(200, text_data="", content_type="text/plain")
        client._session = _mock_session(resp)
        await client.delete_scene("morning")

    async def test_get_config_entries_returns_list(self):
        client = _make_client()
        resp = _make_response(200, json_data=[{"entry_id": "abc", "domain": "zha"}])
        client._session = _mock_session(resp)
        result = await client.get_config_entries()
        assert len(result) == 1

    async def test_get_config_entries_non_list_returns_empty(self):
        client = _make_client()
        resp = _make_response(200, json_data={"error": "something"})
        client._session = _mock_session(resp)
        result = await client.get_config_entries()
        assert result == []

    async def test_check_config(self):
        client = _make_client()
        resp = _make_response(200, json_data={"result": "valid"})
        client._session = _mock_session(resp)
        result = await client.check_config()
        assert result == {"result": "valid"}


class TestHAClientErrors:
    async def test_auth_error_on_401(self):
        client = _make_client()
        resp = _make_response(401)
        resp.raise_for_status = MagicMock()
        client._session = _mock_session(resp)
        with pytest.raises(HAAuthError):
            await client.get_states()

    async def test_connection_error_on_500(self):
        client = _make_client()
        resp = _make_response(500)
        client._session = _mock_session(resp)
        with pytest.raises(HAConnectionError):
            await client.get_states()

    async def test_retries_on_network_error_then_fails(self):
        client = _make_client()

        session = MagicMock()
        call_count = 0

        @asynccontextmanager
        async def _failing_request(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            raise Exception("connection refused")
            yield  # make generator

        session.request = _failing_request
        client._session = session

        with patch("app.ha.client.asyncio.sleep", AsyncMock()):
            with pytest.raises(HAConnectionError):
                await client.get_states()

        assert call_count == 4  # 3 retries + 1 final

    async def test_get_camera_image_success(self):
        client = _make_client()
        resp = MagicMock()
        resp.status = 200
        resp.raise_for_status = MagicMock()
        resp.read = AsyncMock(return_value=b"\xff\xd8\xff")  # JPEG header

        session = MagicMock()

        @asynccontextmanager
        async def _get(*args, **kwargs):
            yield resp

        session.get = _get
        client._session = session

        result = await client.get_camera_image("camera.front_door")
        assert result == b"\xff\xd8\xff"

    async def test_get_camera_image_auth_error(self):
        client = _make_client()
        resp = MagicMock()
        resp.status = 401
        resp.raise_for_status = MagicMock()

        session = MagicMock()

        @asynccontextmanager
        async def _get(*args, **kwargs):
            yield resp

        session.get = _get
        client._session = session

        with pytest.raises(HAAuthError):
            await client.get_camera_image("camera.front_door")
