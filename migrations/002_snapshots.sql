-- Migration 002: Entity snapshots table

CREATE TABLE IF NOT EXISTS entity_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    timestamp TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    user_id INTEGER NOT NULL,
    states TEXT NOT NULL,
    entity_count INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_snapshot_name ON entity_snapshots(name);
CREATE INDEX IF NOT EXISTS idx_snapshot_user ON entity_snapshots(user_id, timestamp);
