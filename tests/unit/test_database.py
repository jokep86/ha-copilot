"""
Unit tests for Database (using in-memory SQLite).
"""
from __future__ import annotations

import asyncio
from pathlib import Path
import pytest

from app.database import Database


async def _connected_db(tmp_path: Path) -> Database:
    db = Database(db_path=tmp_path / "test.db", migrations_dir=tmp_path / "migrations")
    await db.connect()
    return db


async def _setup_tables(db: Database) -> None:
    """Create minimal tables needed for maintenance tests."""
    await db.conn.executescript("""
        CREATE TABLE IF NOT EXISTS ai_audit_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
            trace_id TEXT NOT NULL DEFAULT '',
            user_id INTEGER NOT NULL DEFAULT 0,
            raw_prompt TEXT NOT NULL DEFAULT '',
            raw_response TEXT NOT NULL DEFAULT '',
            parsed_actions TEXT NOT NULL DEFAULT '',
            final_action_taken TEXT,
            prompt_version TEXT NOT NULL DEFAULT 'v1',
            model TEXT NOT NULL DEFAULT 'test',
            input_tokens INTEGER NOT NULL DEFAULT 0,
            output_tokens INTEGER NOT NULL DEFAULT 0,
            latency_ms INTEGER,
            success BOOLEAN NOT NULL DEFAULT 1
        );
        CREATE TABLE IF NOT EXISTS notification_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
            event_type TEXT NOT NULL DEFAULT 'test',
            message TEXT NOT NULL DEFAULT '',
            chat_id INTEGER NOT NULL DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS alert_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
            alert_type TEXT NOT NULL DEFAULT 'test',
            severity TEXT NOT NULL DEFAULT 'info',
            description TEXT NOT NULL DEFAULT '',
            risk_score INTEGER NOT NULL DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS raw_api_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
            user_id INTEGER NOT NULL DEFAULT 0,
            method TEXT NOT NULL DEFAULT 'GET',
            path TEXT NOT NULL DEFAULT '/'
        );
        CREATE TABLE IF NOT EXISTS incident_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
            incident_type TEXT NOT NULL DEFAULT 'test',
            severity TEXT NOT NULL DEFAULT 'info',
            description TEXT NOT NULL DEFAULT '',
            detection_method TEXT NOT NULL DEFAULT 'test'
        );
        CREATE TABLE IF NOT EXISTS ai_cache (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            query_hash TEXT NOT NULL UNIQUE,
            query_text TEXT NOT NULL DEFAULT '',
            response TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
            ttl_seconds INTEGER NOT NULL DEFAULT 3600
        );
        CREATE TABLE IF NOT EXISTS undo_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
            user_id INTEGER NOT NULL DEFAULT 0,
            action_type TEXT NOT NULL DEFAULT 'test',
            previous_state TEXT NOT NULL DEFAULT '',
            ttl_seconds INTEGER NOT NULL DEFAULT 600,
            used BOOLEAN DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS conversation_context (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL DEFAULT 0,
            timestamp TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
            role TEXT NOT NULL DEFAULT 'user',
            content TEXT NOT NULL DEFAULT ''
        );
        CREATE TABLE IF NOT EXISTS app_settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
        );
    """)
    await db.conn.commit()


class TestDatabaseLifecycle:
    async def test_connect_creates_file(self, tmp_path):
        db_path = tmp_path / "test.db"
        db = Database(db_path=db_path, migrations_dir=tmp_path)
        await db.connect()
        assert db._conn is not None
        assert db_path.exists()
        await db.disconnect()

    async def test_disconnect_closes_connection(self, tmp_path):
        db = await _connected_db(tmp_path)
        await db.disconnect()
        assert db._conn is None

    async def test_conn_raises_when_not_connected(self, tmp_path):
        db = Database(db_path=tmp_path / "test.db")
        with pytest.raises(RuntimeError):
            _ = db.conn

    async def test_disconnect_without_connect_is_noop(self, tmp_path):
        db = Database(db_path=tmp_path / "test.db")
        await db.disconnect()  # Should not raise

    async def test_connect_creates_parent_dirs(self, tmp_path):
        nested_path = tmp_path / "a" / "b" / "c" / "test.db"
        db = Database(db_path=nested_path, migrations_dir=tmp_path)
        await db.connect()
        assert nested_path.exists()
        await db.disconnect()


class TestDatabaseMigrations:
    async def test_run_migrations_with_no_files(self, tmp_path):
        db = await _connected_db(tmp_path)
        # No migration files in empty tmp_path/migrations
        (tmp_path / "migrations").mkdir(exist_ok=True)
        db.migrations_dir = tmp_path / "migrations"
        await db.run_migrations()  # Should not raise
        await db.disconnect()

    async def test_run_migrations_applies_sql_file(self, tmp_path):
        migrations_dir = tmp_path / "migrations"
        migrations_dir.mkdir()
        sql_file = migrations_dir / "001_test.sql"
        sql_file.write_text("CREATE TABLE IF NOT EXISTS test_table (id INTEGER PRIMARY KEY);")

        db = Database(db_path=tmp_path / "test.db", migrations_dir=migrations_dir)
        await db.connect()
        await db.run_migrations()

        cursor = await db.conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='test_table'"
        )
        row = await cursor.fetchone()
        assert row is not None
        await db.disconnect()

    async def test_run_migrations_skips_already_applied(self, tmp_path):
        migrations_dir = tmp_path / "migrations"
        migrations_dir.mkdir()
        sql_file = migrations_dir / "001_test.sql"
        sql_file.write_text("CREATE TABLE IF NOT EXISTS migration_once (id INTEGER PRIMARY KEY);")

        db = Database(db_path=tmp_path / "test.db", migrations_dir=migrations_dir)
        await db.connect()
        await db.run_migrations()
        await db.run_migrations()  # Second run should be a no-op
        await db.disconnect()


class TestDatabaseMaintenance:
    async def test_purge_old_records_runs_without_error(self, tmp_path):
        db = await _connected_db(tmp_path)
        await _setup_tables(db)
        await db.purge_old_records(purge_days=90)
        await db.disconnect()

    async def test_purge_expired_cache(self, tmp_path):
        db = await _connected_db(tmp_path)
        await _setup_tables(db)
        # Insert an expired cache entry
        await db.conn.execute(
            "INSERT INTO ai_cache (query_hash, ttl_seconds) VALUES ('hash1', 1)"
        )
        await db.conn.commit()
        await asyncio.sleep(0.1)
        await db.purge_expired_cache()
        await db.disconnect()

    async def test_purge_expired_undo(self, tmp_path):
        db = await _connected_db(tmp_path)
        await _setup_tables(db)
        await db.purge_expired_undo()
        await db.disconnect()

    async def test_purge_old_conversation_context(self, tmp_path):
        db = await _connected_db(tmp_path)
        await _setup_tables(db)
        await db.purge_old_conversation_context(ttl_minutes=30)
        await db.disconnect()

    async def test_vacuum(self, tmp_path):
        db = await _connected_db(tmp_path)
        await db.vacuum()
        await db.disconnect()

    async def test_get_size_bytes_existing_file(self, tmp_path):
        db = await _connected_db(tmp_path)
        size = await db.get_size_bytes()
        assert size > 0
        await db.disconnect()

    async def test_get_size_bytes_nonexistent_file(self, tmp_path):
        db = Database(db_path=tmp_path / "nonexistent.db")
        size = await db.get_size_bytes()
        assert size == 0


class TestDatabaseSettings:
    async def test_get_setting_missing_returns_default(self, tmp_path):
        db = await _connected_db(tmp_path)
        await _setup_tables(db)
        val = await db.get_setting("missing_key", default="fallback")
        assert val == "fallback"
        await db.disconnect()

    async def test_set_and_get_setting(self, tmp_path):
        db = await _connected_db(tmp_path)
        await _setup_tables(db)
        await db.set_setting("onboarded", "true")
        val = await db.get_setting("onboarded")
        assert val == "true"
        await db.disconnect()

    async def test_set_setting_upsert(self, tmp_path):
        db = await _connected_db(tmp_path)
        await _setup_tables(db)
        await db.set_setting("theme", "light")
        await db.set_setting("theme", "dark")
        val = await db.get_setting("theme")
        assert val == "dark"
        await db.disconnect()
