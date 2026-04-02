"""
Unit tests for AIAuditLog.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
import pytest

from app.ai.audit import AIAuditLog


def _make_db():
    conn = MagicMock()
    conn.execute = AsyncMock()
    conn.commit = AsyncMock()

    cursor = MagicMock()
    cursor.fetchone = AsyncMock(return_value=(1500,))
    cursor.fetchall = AsyncMock(return_value=[
        ("2026-04-01", "claude-sonnet-4-6", 1000, 500, 5),
    ])
    conn.execute = AsyncMock(return_value=cursor)

    db = MagicMock()
    db.conn = conn
    return db


def _make_response(
    trace_id="abc123",
    model="claude-sonnet-4-6",
    input_tokens=100,
    output_tokens=50,
    raw_response="response text",
    prompt_version="v1",
    actions=None,
):
    from app.schemas.ai_action import AIAction, ActionType
    resp = MagicMock()
    resp.trace_id = trace_id
    resp.model = model
    resp.input_tokens = input_tokens
    resp.output_tokens = output_tokens
    resp.raw_response = raw_response
    resp.prompt_version = prompt_version
    resp.actions = actions or [AIAction(action_type=ActionType.CALL_SERVICE)]
    return resp


class TestAIAuditLog:
    async def test_log_executes_insert(self):
        db = _make_db()
        audit = AIAuditLog(db)
        resp = _make_response()
        await audit.log(resp, user_id=12345, raw_prompt="turn on lights")
        assert db.conn.execute.await_count >= 2  # INSERT + UPSERT
        db.conn.commit.assert_awaited_once()

    async def test_log_with_final_action_and_latency(self):
        db = _make_db()
        audit = AIAuditLog(db)
        resp = _make_response()
        await audit.log(
            resp,
            user_id=12345,
            raw_prompt="turn on lights",
            final_action="light.turn_on",
            latency_ms=250,
            success=True,
        )
        # Verify the INSERT call contains the values
        calls = db.conn.execute.call_args_list
        insert_call = calls[0]
        params = insert_call[0][1]  # positional tuple
        assert "abc123" in params  # trace_id
        assert 12345 in params     # user_id
        assert "turn on lights" in params
        assert 250 in params       # latency_ms

    async def test_log_failure_case(self):
        db = _make_db()
        audit = AIAuditLog(db)
        resp = _make_response()
        await audit.log(
            resp,
            user_id=1,
            raw_prompt="test",
            success=False,
        )
        params = db.conn.execute.call_args_list[0][0][1]
        assert False in params  # success=False

    async def test_get_daily_tokens_used(self):
        db = _make_db()
        cursor = MagicMock()
        cursor.fetchone = AsyncMock(return_value=(2500,))
        db.conn.execute = AsyncMock(return_value=cursor)

        audit = AIAuditLog(db)
        tokens = await audit.get_daily_tokens_used()
        assert tokens == 2500

    async def test_get_daily_tokens_used_none_row(self):
        db = _make_db()
        cursor = MagicMock()
        cursor.fetchone = AsyncMock(return_value=None)
        db.conn.execute = AsyncMock(return_value=cursor)

        audit = AIAuditLog(db)
        tokens = await audit.get_daily_tokens_used()
        assert tokens == 0

    async def test_get_stats_returns_rows(self):
        db = _make_db()
        cursor = MagicMock()
        cursor.fetchall = AsyncMock(return_value=[
            ("2026-04-01", "claude-sonnet-4-6", 1000, 500, 5),
            ("2026-03-31", "claude-sonnet-4-6", 800, 400, 4),
        ])
        db.conn.execute = AsyncMock(return_value=cursor)

        audit = AIAuditLog(db)
        stats = await audit.get_stats(days=30)
        assert stats["days"] == 30
        assert len(stats["rows"]) == 2
        assert stats["rows"][0]["model"] == "claude-sonnet-4-6"
        assert stats["rows"][0]["requests"] == 5

    async def test_get_stats_empty(self):
        db = _make_db()
        cursor = MagicMock()
        cursor.fetchall = AsyncMock(return_value=[])
        db.conn.execute = AsyncMock(return_value=cursor)

        audit = AIAuditLog(db)
        stats = await audit.get_stats(days=7)
        assert stats["days"] == 7
        assert stats["rows"] == []
