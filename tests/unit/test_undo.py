"""
Unit tests for UndoManager.
Covers: save, undo_last (on/off, numeric, no-op, failure), get_pending.
"""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, call

import pytest

from app.undo.manager import UndoManager


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_cursor(row=None, rows=None):
    cursor = AsyncMock()
    cursor.fetchone = AsyncMock(return_value=row)
    cursor.fetchall = AsyncMock(return_value=rows or [])
    return cursor


def _make_undo(row=None, rows=None, ttl=600):
    cursor = _make_cursor(row=row, rows=rows)
    db = MagicMock()
    db.conn = AsyncMock()
    db.conn.execute = AsyncMock(return_value=cursor)
    db.conn.commit = AsyncMock()

    ha = MagicMock()
    ha.call_service = AsyncMock()

    mgr = UndoManager(db=db, ha_client=ha, ttl_seconds=ttl)
    return mgr, db, ha, cursor


# ---------------------------------------------------------------------------
# save
# ---------------------------------------------------------------------------

class TestSave:
    async def test_inserts_row_and_commits(self):
        mgr, db, ha, _ = _make_undo()
        await mgr.save(
            user_id=42,
            action_type="toggle",
            entity_id="light.sala",
            previous_state={"state": "on"},
        )
        db.conn.execute.assert_awaited_once()
        db.conn.commit.assert_awaited_once()

    async def test_serializes_state_as_json(self):
        mgr, db, ha, _ = _make_undo()
        state = {"state": "on", "attributes": {"brightness": 200}}
        await mgr.save(42, "toggle", "light.sala", state)
        # Second positional arg to execute is the tuple; third element is the JSON
        call_args = db.conn.execute.call_args[0][1]
        stored_json = call_args[3]
        assert json.loads(stored_json) == state

    async def test_stores_ttl(self):
        mgr, db, ha, _ = _make_undo(ttl=300)
        await mgr.save(42, "toggle", "light.sala", {"state": "off"})
        call_args = db.conn.execute.call_args[0][1]
        assert call_args[4] == 300


# ---------------------------------------------------------------------------
# undo_last — nothing to undo
# ---------------------------------------------------------------------------

class TestUndoLastNoOp:
    async def test_returns_none_when_no_pending(self):
        mgr, db, ha, _ = _make_undo(row=None)
        result = await mgr.undo_last(user_id=42)
        assert result is None
        ha.call_service.assert_not_awaited()


# ---------------------------------------------------------------------------
# undo_last — turn_on / turn_off
# ---------------------------------------------------------------------------

class TestUndoLastOnOff:
    async def test_reverts_to_on(self):
        prev = json.dumps({"state": "on"})
        row = (1, "toggle", "light.sala", prev)
        mgr, db, ha, _ = _make_undo(row=row)

        result = await mgr.undo_last(42)

        ha.call_service.assert_awaited_once_with("light", "turn_on", {"entity_id": "light.sala"})
        assert "light.sala" in result
        assert "on" in result

    async def test_reverts_to_off(self):
        prev = json.dumps({"state": "off"})
        row = (2, "toggle", "switch.fan", prev)
        mgr, db, ha, _ = _make_undo(row=row)

        result = await mgr.undo_last(42)

        ha.call_service.assert_awaited_once_with("switch", "turn_off", {"entity_id": "switch.fan"})
        assert "off" in result

    async def test_marks_row_as_used_after_revert(self):
        prev = json.dumps({"state": "on"})
        row = (7, "toggle", "light.sala", prev)
        mgr, db, ha, _ = _make_undo(row=row)

        await mgr.undo_last(42)

        # The second execute call should be the MARK_USED UPDATE
        calls = db.conn.execute.call_args_list
        assert len(calls) == 2
        assert "UPDATE" in calls[1][0][0].upper()

    async def test_commits_after_mark_used(self):
        prev = json.dumps({"state": "on"})
        row = (3, "toggle", "light.sala", prev)
        mgr, db, ha, _ = _make_undo(row=row)

        await mgr.undo_last(42)

        # Two commits: one in save, one in undo_last
        assert db.conn.commit.await_count >= 1


# ---------------------------------------------------------------------------
# undo_last — numeric state (brightness)
# ---------------------------------------------------------------------------

class TestUndoLastNumeric:
    async def test_reverts_brightness(self):
        prev = json.dumps({"state": "200", "attributes": {"brightness": 150}})
        row = (4, "dim", "light.sala", prev)
        mgr, db, ha, _ = _make_undo(row=row)

        await mgr.undo_last(42)

        ha.call_service.assert_awaited_once_with(
            "light", "set_value",
            {"entity_id": "light.sala", "brightness": 150},
        )

    async def test_reverts_climate_temperature(self):
        prev = json.dumps({"state": "22.0", "attributes": {"temperature": 20.0}})
        row = (5, "set_temp", "climate.living", prev)
        mgr, db, ha, _ = _make_undo(row=row)

        await mgr.undo_last(42)

        ha.call_service.assert_awaited_once_with(
            "climate", "set_value",
            {"entity_id": "climate.living", "temperature": 20.0},
        )


# ---------------------------------------------------------------------------
# undo_last — HA call failure
# ---------------------------------------------------------------------------

class TestUndoLastFailure:
    async def test_returns_error_message_on_ha_failure(self):
        prev = json.dumps({"state": "on"})
        row = (6, "toggle", "light.sala", prev)
        mgr, db, ha, _ = _make_undo(row=row)
        ha.call_service = AsyncMock(side_effect=Exception("HA unreachable"))

        result = await mgr.undo_last(42)

        assert result is not None
        assert "Undo failed" in result
        assert "light.sala" in result


# ---------------------------------------------------------------------------
# get_pending
# ---------------------------------------------------------------------------

class TestGetPending:
    async def test_returns_empty_when_nothing_pending(self):
        mgr, db, ha, _ = _make_undo(rows=[])
        result = await mgr.get_pending(42)
        assert result == []

    async def test_returns_pending_items(self):
        rows = [
            ("toggle", "light.sala", "2026-03-25T10:00:00Z"),
            ("dim", "light.kitchen", "2026-03-25T10:01:00Z"),
        ]
        mgr, db, ha, _ = _make_undo(rows=rows)
        result = await mgr.get_pending(42)

        assert len(result) == 2
        assert result[0]["entity_id"] == "light.sala"
        assert result[0]["action"] == "toggle"
        assert result[1]["entity_id"] == "light.kitchen"
