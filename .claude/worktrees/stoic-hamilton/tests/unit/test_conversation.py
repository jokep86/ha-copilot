"""
Unit tests for ConversationMemory.
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock
import pytest

from app.ai.conversation import ConversationMemory


def _make_db():
    conn = MagicMock()
    conn.execute = AsyncMock()
    conn.commit = AsyncMock()
    cursor = MagicMock()
    cursor.fetchall = AsyncMock(return_value=[])
    conn.execute.return_value = cursor
    db = MagicMock()
    db.conn = conn
    return db, conn, cursor


class TestConversationMemory:
    async def test_disabled_add_does_nothing(self):
        db, conn, _ = _make_db()
        mem = ConversationMemory(db=db, enabled=False, ttl_minutes=30, max_messages=10)
        await mem.add(user_id=1, role="user", content="hello")
        conn.execute.assert_not_awaited()

    async def test_enabled_add_inserts_row(self):
        db, conn, cursor = _make_db()
        mem = ConversationMemory(db=db, enabled=True, ttl_minutes=30, max_messages=10)
        await mem.add(user_id=1, role="user", content="hello", trace_id="t1")
        conn.execute.assert_awaited_once()
        conn.commit.assert_awaited_once()

    async def test_disabled_get_returns_empty(self):
        db, conn, _ = _make_db()
        mem = ConversationMemory(db=db, enabled=False, ttl_minutes=30, max_messages=10)
        result = await mem.get_history(user_id=1)
        assert result == []
        conn.execute.assert_not_awaited()

    async def test_enabled_get_queries_db(self):
        db, conn, cursor = _make_db()
        cursor.fetchall = AsyncMock(return_value=[
            ("user", "turn on the lights"),
            ("assistant", "Turning on lights."),
        ])
        mem = ConversationMemory(db=db, enabled=True, ttl_minutes=30, max_messages=10)
        result = await mem.get_history(user_id=1)
        assert len(result) == 2
        assert result[0]["role"] == "user"
        assert result[1]["role"] == "assistant"

    async def test_purge_user_executes(self):
        db, conn, _ = _make_db()
        mem = ConversationMemory(db=db, enabled=True, ttl_minutes=30, max_messages=10)
        await mem.purge_user(user_id=1)
        conn.execute.assert_awaited_once()
        conn.commit.assert_awaited_once()
