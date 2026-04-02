"""
Unit tests for RawApiModule.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
from contextlib import asynccontextmanager
import pytest

from app.modules.raw_api import RawApiModule


def _make_app():
    db = MagicMock()
    db.conn = MagicMock()
    db.conn.execute = AsyncMock()
    db.conn.commit = AsyncMock()

    app = MagicMock()
    app.db = db
    return app


def _make_context():
    ctx = MagicMock()
    ctx.update = MagicMock()
    ctx.update.message = MagicMock()
    ctx.update.message.reply_text = AsyncMock()
    ctx.user_id = 12345
    return ctx


def _make_mock_response(status=200, text='{"state": "on"}'):
    resp = MagicMock()
    resp.status = status
    resp.text = AsyncMock(return_value=text)
    return resp


class TestRawApiModule:
    async def test_setup(self):
        mod = RawApiModule()
        app = _make_app()
        await mod.setup(app)
        assert mod._app is app

    async def test_teardown_is_noop(self):
        mod = RawApiModule()
        app = _make_app()
        await mod.setup(app)
        await mod.teardown()

    async def test_module_attributes(self):
        mod = RawApiModule()
        assert "raw" in mod.commands
        assert mod.name == "raw_api"

    async def test_no_args_shows_usage(self):
        mod = RawApiModule()
        app = _make_app()
        await mod.setup(app)
        ctx = _make_context()
        await mod.handle_command("raw", [], ctx)
        text = ctx.update.message.reply_text.call_args[0][0]
        assert "Usage" in text or "Raw API" in text

    async def test_missing_method_error(self):
        mod = RawApiModule()
        app = _make_app()
        await mod.setup(app)
        ctx = _make_context()
        # SUP with no more args
        await mod.handle_command("raw", ["SUP"], ctx)
        text = ctx.update.message.reply_text.call_args[0][0]
        assert "Missing HTTP method" in text

    async def test_unknown_method_error(self):
        mod = RawApiModule()
        app = _make_app()
        await mod.setup(app)
        ctx = _make_context()
        await mod.handle_command("raw", ["INVALIDMETHOD", "/api/test"], ctx)
        text = ctx.update.message.reply_text.call_args[0][0]
        assert "Unknown method" in text

    async def test_missing_path_error(self):
        mod = RawApiModule()
        app = _make_app()
        await mod.setup(app)
        ctx = _make_context()
        await mod.handle_command("raw", ["GET"], ctx)
        text = ctx.update.message.reply_text.call_args[0][0]
        assert "Missing path" in text

    async def test_post_without_confirm_shows_prompt(self):
        mod = RawApiModule()
        app = _make_app()
        await mod.setup(app)
        ctx = _make_context()
        await mod.handle_command("raw", ["POST", "/api/services/light/turn_on"], ctx)
        text = ctx.update.message.reply_text.call_args[0][0]
        # Should prompt for confirmation
        assert "confirm" in text.lower() or "⚠️" in text

    async def test_invalid_json_body_error(self):
        mod = RawApiModule()
        app = _make_app()
        await mod.setup(app)
        ctx = _make_context()
        await mod.handle_command(
            "raw", ["POST", "confirm", "/api/services/light/turn_on", "{bad json}"], ctx
        )
        text = ctx.update.message.reply_text.call_args[0][0]
        assert "Invalid JSON" in text

    async def test_get_request_executes(self):
        mod = RawApiModule()
        app = _make_app()
        await mod.setup(app)
        ctx = _make_context()

        mock_resp = _make_mock_response(200, '{"state": "on"}')

        @asynccontextmanager
        async def _mock_request(*args, **kwargs):
            yield mock_resp

        mock_session = MagicMock()
        mock_session.request = _mock_request

        @asynccontextmanager
        async def _mock_client_session(*args, **kwargs):
            yield mock_session

        with patch("app.modules.raw_api.aiohttp.ClientSession", _mock_client_session):
            await mod.handle_command("raw", ["GET", "/api/states/light.sala"], ctx)

        text = ctx.update.message.reply_text.call_args[0][0]
        assert "GET" in text
        assert "200" in text

    async def test_post_with_confirm_executes(self):
        mod = RawApiModule()
        app = _make_app()
        await mod.setup(app)
        ctx = _make_context()

        mock_resp = _make_mock_response(200, '{"result": "ok"}')

        @asynccontextmanager
        async def _mock_request(*args, **kwargs):
            yield mock_resp

        mock_session = MagicMock()
        mock_session.request = _mock_request

        @asynccontextmanager
        async def _mock_client_session(*args, **kwargs):
            yield mock_session

        with patch("app.modules.raw_api.aiohttp.ClientSession", _mock_client_session):
            await mod.handle_command(
                "raw",
                ["POST", "confirm", "/api/services/light/turn_on", '{"entity_id":"light.sala"}'],
                ctx,
            )

        text = ctx.update.message.reply_text.call_args[0][0]
        assert "POST" in text

    async def test_sup_prefix_sets_supervisor_flag(self):
        mod = RawApiModule()
        app = _make_app()
        await mod.setup(app)
        ctx = _make_context()

        mock_resp = _make_mock_response(200, '{"supervisor": "info"}')

        @asynccontextmanager
        async def _mock_request(*args, **kwargs):
            yield mock_resp

        mock_session = MagicMock()
        mock_session.request = _mock_request

        @asynccontextmanager
        async def _mock_client_session(*args, **kwargs):
            yield mock_session

        with patch("app.modules.raw_api.aiohttp.ClientSession", _mock_client_session):
            await mod.handle_command("raw", ["SUP", "GET", "/supervisor/info"], ctx)

        text = ctx.update.message.reply_text.call_args[0][0]
        assert "GET" in text

    async def test_request_failure_shows_error(self):
        mod = RawApiModule()
        app = _make_app()
        await mod.setup(app)
        ctx = _make_context()

        import aiohttp as _aiohttp

        @asynccontextmanager
        async def _mock_client_session(*args, **kwargs):
            raise _aiohttp.ClientError("connection refused")
            yield  # make it a generator

        with patch("app.modules.raw_api.aiohttp.ClientSession", side_effect=_aiohttp.ClientError("connection refused")):
            await mod.handle_command("raw", ["GET", "/api/states"], ctx)

        text = ctx.update.message.reply_text.call_args[0][0]
        assert "failed" in text.lower() or "connection refused" in text

    async def test_error_response_status(self):
        mod = RawApiModule()
        app = _make_app()
        await mod.setup(app)
        ctx = _make_context()

        mock_resp = _make_mock_response(404, '{"message": "not found"}')

        @asynccontextmanager
        async def _mock_request(*args, **kwargs):
            yield mock_resp

        mock_session = MagicMock()
        mock_session.request = _mock_request

        @asynccontextmanager
        async def _mock_client_session(*args, **kwargs):
            yield mock_session

        with patch("app.modules.raw_api.aiohttp.ClientSession", _mock_client_session):
            await mod.handle_command("raw", ["GET", "/api/nonexistent"], ctx)

        text = ctx.update.message.reply_text.call_args[0][0]
        assert "404" in text

    async def test_long_response_truncated(self):
        mod = RawApiModule()
        app = _make_app()
        await mod.setup(app)
        ctx = _make_context()

        long_response = '{"data": "' + "x" * 4000 + '"}'
        mock_resp = _make_mock_response(200, long_response)

        @asynccontextmanager
        async def _mock_request(*args, **kwargs):
            yield mock_resp

        mock_session = MagicMock()
        mock_session.request = _mock_request

        @asynccontextmanager
        async def _mock_client_session(*args, **kwargs):
            yield mock_session

        with patch("app.modules.raw_api.aiohttp.ClientSession", _mock_client_session):
            await mod.handle_command("raw", ["GET", "/api/states"], ctx)

        text = ctx.update.message.reply_text.call_args[0][0]
        assert "truncated" in text
