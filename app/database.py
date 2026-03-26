"""
SQLite database — setup, migrations, and maintenance via aiosqlite.
DB file: /data/ha_copilot.db  (override via HA_DB_PATH env var)
Migrations dir: /app/migrations  (override via HA_MIGRATIONS_DIR env var)
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

import aiosqlite

from app.observability.logger import get_logger

logger = get_logger(__name__)

DB_PATH = Path(os.environ.get("HA_DB_PATH", "/data/ha_copilot.db"))
MIGRATIONS_DIR = Path(os.environ.get("HA_MIGRATIONS_DIR", "/app/migrations"))


class Database:
    def __init__(
        self,
        db_path: Path = DB_PATH,
        migrations_dir: Path = MIGRATIONS_DIR,
    ) -> None:
        self.db_path = db_path
        self.migrations_dir = migrations_dir
        self._conn: Optional[aiosqlite.Connection] = None

    async def connect(self) -> None:
        """Open the database connection and configure pragmas."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = await aiosqlite.connect(str(self.db_path))
        self._conn.row_factory = aiosqlite.Row
        await self._conn.execute("PRAGMA journal_mode=WAL")
        await self._conn.execute("PRAGMA foreign_keys=ON")
        await self._conn.commit()
        logger.info("database_connected", path=str(self.db_path))

    async def disconnect(self) -> None:
        if self._conn:
            await self._conn.close()
            self._conn = None
            logger.info("database_disconnected")

    @property
    def conn(self) -> aiosqlite.Connection:
        if not self._conn:
            raise RuntimeError("Database not connected — call connect() first")
        return self._conn

    async def run_migrations(self) -> None:
        """Run all pending SQL migration files in version order."""
        await self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_version (
                version INTEGER PRIMARY KEY,
                applied_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
            )
            """
        )
        await self.conn.commit()

        cursor = await self.conn.execute("SELECT version FROM schema_version ORDER BY version")
        rows = await cursor.fetchall()
        applied = {row[0] for row in rows}

        migration_files = sorted(self.migrations_dir.glob("*.sql"))
        for mf in migration_files:
            try:
                version = int(mf.stem.split("_")[0])
            except (ValueError, IndexError):
                continue

            if version in applied:
                continue

            logger.info("applying_migration", file=mf.name, version=version)
            sql = mf.read_text()
            await self.conn.executescript(sql)
            await self.conn.execute(
                "INSERT INTO schema_version (version) VALUES (?)", (version,)
            )
            await self.conn.commit()
            logger.info("migration_applied", version=version)

    # --- Maintenance ---

    async def purge_old_records(self, purge_days: int = 90) -> None:
        """Remove records older than purge_days from log tables."""
        tables = [
            ("ai_audit_log", "timestamp"),
            ("notification_log", "timestamp"),
            ("alert_log", "timestamp"),
            ("raw_api_log", "timestamp"),
            ("incident_log", "timestamp"),
        ]
        for table, col in tables:
            cursor = await self.conn.execute(
                f"DELETE FROM {table} WHERE {col} < datetime('now', ?)",
                (f"-{purge_days} days",),
            )
            await self.conn.commit()
            if cursor.rowcount:
                logger.info("purged_old_records", table=table, count=cursor.rowcount)

    async def purge_expired_cache(self) -> None:
        """Remove expired AI cache entries."""
        cursor = await self.conn.execute(
            "DELETE FROM ai_cache "
            "WHERE datetime(created_at, '+' || ttl_seconds || ' seconds') < datetime('now')"
        )
        await self.conn.commit()
        if cursor.rowcount:
            logger.info("purged_expired_cache", count=cursor.rowcount)

    async def purge_expired_undo(self) -> None:
        """Remove expired undo log entries."""
        cursor = await self.conn.execute(
            "DELETE FROM undo_log "
            "WHERE datetime(timestamp, '+' || ttl_seconds || ' seconds') < datetime('now')"
        )
        await self.conn.commit()
        if cursor.rowcount:
            logger.info("purged_expired_undo", count=cursor.rowcount)

    async def purge_old_conversation_context(self, ttl_minutes: int = 30) -> None:
        """Remove conversation context older than TTL."""
        cursor = await self.conn.execute(
            "DELETE FROM conversation_context WHERE timestamp < datetime('now', ?)",
            (f"-{ttl_minutes} minutes",),
        )
        await self.conn.commit()
        if cursor.rowcount:
            logger.info("purged_conversation_context", count=cursor.rowcount)

    async def vacuum(self) -> None:
        """VACUUM to reclaim space. Run weekly."""
        await self.conn.execute("VACUUM")
        logger.info("database_vacuumed")

    async def get_size_bytes(self) -> int:
        """Return current DB file size in bytes."""
        return self.db_path.stat().st_size if self.db_path.exists() else 0

    # --- App settings ---

    async def get_setting(self, key: str, default: str | None = None) -> str | None:
        """Read a key from app_settings. Returns default if not found."""
        cursor = await self.conn.execute(
            "SELECT value FROM app_settings WHERE key = ?", (key,)
        )
        row = await cursor.fetchone()
        return row[0] if row else default

    async def set_setting(self, key: str, value: str) -> None:
        """Write or update a key in app_settings."""
        await self.conn.execute(
            """
            INSERT INTO app_settings (key, value, updated_at)
            VALUES (?, ?, strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
            ON CONFLICT(key) DO UPDATE SET
                value = excluded.value,
                updated_at = excluded.updated_at
            """,
            (key, value),
        )
        await self.conn.commit()
