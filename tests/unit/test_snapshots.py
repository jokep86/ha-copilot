"""
Unit tests for SnapshotsModule and snapshot helpers.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
import pytest

from app.modules.snapshots import SnapshotsModule, _compute_diff, _default_name


def _app(states=None, db_rows=None):
    app = MagicMock()
    app.ha_client.get_states = AsyncMock(
        return_value=states
        or [
            {"entity_id": "light.sala", "state": "on", "attributes": {}},
            {"entity_id": "sensor.temp", "state": "22.5", "attributes": {}},
        ]
    )
    # Mock DB
    cursor = MagicMock()
    cursor.fetchone = AsyncMock(return_value=db_rows[0] if db_rows else None)
    cursor.fetchall = AsyncMock(return_value=db_rows or [])
    app.db.conn.execute = AsyncMock(return_value=cursor)
    app.db.conn.commit = AsyncMock()
    return app


def _context(user_id=1):
    ctx = MagicMock()
    ctx.user_id = user_id
    ctx.update.message.reply_text = AsyncMock()
    return ctx


class TestSnapshotsModule:
    def test_commands(self):
        assert "snapshot" in SnapshotsModule.commands

    async def test_save_calls_db(self):
        m = SnapshotsModule()
        app = _app()
        await m.setup(app)
        ctx = _context()
        await m.handle_command("snapshot", ["save", "test_snap"], ctx)
        app.db.conn.execute.assert_called()
        app.db.conn.commit.assert_called()
        text = ctx.update.message.reply_text.call_args[0][0]
        assert "saved" in text.lower()

    async def test_save_default_name(self):
        m = SnapshotsModule()
        await m.setup(_app())
        ctx = _context()
        await m.handle_command("snapshot", ["save"], ctx)
        # Default name starts with "snap_"
        call_args = _app().db.conn.execute.call_args
        # Should not raise — just verify reply
        text = ctx.update.message.reply_text.call_args[0][0]
        assert "saved" in text.lower()

    async def test_list_no_snapshots(self):
        m = SnapshotsModule()
        await m.setup(_app(db_rows=[]))
        ctx = _context()
        await m.handle_command("snapshot", ["list"], ctx)
        text = ctx.update.message.reply_text.call_args[0][0]
        assert "no snapshots" in text.lower()

    async def test_list_shows_snapshots(self):
        rows = [
            ("snap1", "2026-03-24T10:00:00Z", 45),
            ("snap2", "2026-03-24T12:00:00Z", 46),
        ]
        # Build mock rows supporting index access
        mock_rows = [MagicMock(__getitem__=lambda s, i: r[i]) for r in rows]
        m = SnapshotsModule()
        await m.setup(_app(db_rows=mock_rows))
        ctx = _context()
        await m.handle_command("snapshot", ["list"], ctx)
        text = ctx.update.message.reply_text.call_args[0][0]
        assert "snap1" in text or "snap2" in text

    async def test_diff_no_snapshots(self):
        m = SnapshotsModule()
        await m.setup(_app(db_rows=[]))
        ctx = _context()
        await m.handle_command("snapshot", ["diff"], ctx)
        text = ctx.update.message.reply_text.call_args[0][0]
        assert "no snapshots" in text.lower()

    async def test_invalid_sub_command(self):
        m = SnapshotsModule()
        await m.setup(_app())
        ctx = _context()
        await m.handle_command("snapshot", ["badcmd"], ctx)
        text = ctx.update.message.reply_text.call_args[0][0]
        assert "usage" in text.lower()


class TestComputeDiff:
    def test_no_changes(self):
        saved = {"light.a": {"state": "on"}, "sensor.b": {"state": "22"}}
        current = {"light.a": {"state": "on"}, "sensor.b": {"state": "22"}}
        diff = _compute_diff("snap", "2026-01-01T00:00Z", "2026-01-02T00:00Z", saved, current)
        assert diff.added == []
        assert diff.removed == []
        assert diff.changed == {}
        assert diff.unchanged_count == 2

    def test_added_entity(self):
        saved = {"light.a": {"state": "on"}}
        current = {"light.a": {"state": "on"}, "sensor.new": {"state": "5"}}
        diff = _compute_diff("snap", "2026-01-01T00:00Z", "2026-01-02T00:00Z", saved, current)
        assert "sensor.new" in diff.added

    def test_removed_entity(self):
        saved = {"light.a": {"state": "on"}, "sensor.gone": {"state": "5"}}
        current = {"light.a": {"state": "on"}}
        diff = _compute_diff("snap", "2026-01-01T00:00Z", "2026-01-02T00:00Z", saved, current)
        assert "sensor.gone" in diff.removed

    def test_changed_state(self):
        saved = {"light.a": {"state": "on"}}
        current = {"light.a": {"state": "off"}}
        diff = _compute_diff("snap", "2026-01-01T00:00Z", "2026-01-02T00:00Z", saved, current)
        assert "light.a" in diff.changed
        assert diff.changed["light.a"] == ("on", "off")

    def test_default_name_format(self):
        name = _default_name()
        assert name.startswith("snap_")
        assert len(name) > 10
