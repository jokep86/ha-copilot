-- Migration 001: Initial schema
-- All tables for ha-copilot v0.1.0

CREATE TABLE IF NOT EXISTS ai_audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    trace_id TEXT NOT NULL,
    timestamp TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    user_id INTEGER NOT NULL,
    raw_prompt TEXT NOT NULL,
    raw_response TEXT NOT NULL,
    parsed_actions TEXT NOT NULL,
    final_action_taken TEXT,
    prompt_version TEXT NOT NULL,
    model TEXT NOT NULL,
    input_tokens INTEGER NOT NULL,
    output_tokens INTEGER NOT NULL,
    latency_ms INTEGER,
    success BOOLEAN NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS token_usage (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT NOT NULL,
    model TEXT NOT NULL,
    total_input_tokens INTEGER NOT NULL DEFAULT 0,
    total_output_tokens INTEGER NOT NULL DEFAULT 0,
    total_requests INTEGER NOT NULL DEFAULT 0,
    estimated_cost_usd REAL,
    UNIQUE(date, model)
);

CREATE TABLE IF NOT EXISTS notification_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    event_type TEXT NOT NULL,
    entity_id TEXT,
    message TEXT NOT NULL,
    chat_id INTEGER NOT NULL,
    was_auto_fix BOOLEAN DEFAULT 0,
    fix_action TEXT,
    fix_result TEXT
);

CREATE TABLE IF NOT EXISTS alert_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    alert_type TEXT NOT NULL,
    severity TEXT NOT NULL,
    entity_id TEXT,
    description TEXT NOT NULL,
    risk_score INTEGER NOT NULL DEFAULT 0,
    auto_fix_attempted BOOLEAN DEFAULT 0,
    auto_fix_action TEXT,
    auto_fix_result TEXT,
    acknowledged BOOLEAN DEFAULT 0
);

CREATE TABLE IF NOT EXISTS conversation_context (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    timestamp TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    trace_id TEXT
);

CREATE TABLE IF NOT EXISTS ai_cache (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    query_hash TEXT NOT NULL UNIQUE,
    query_text TEXT NOT NULL,
    response TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    ttl_seconds INTEGER NOT NULL DEFAULT 3600
);

CREATE TABLE IF NOT EXISTS undo_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    user_id INTEGER NOT NULL,
    action_type TEXT NOT NULL,
    entity_id TEXT,
    previous_state TEXT NOT NULL,
    ttl_seconds INTEGER NOT NULL DEFAULT 600,
    used BOOLEAN DEFAULT 0
);

CREATE TABLE IF NOT EXISTS raw_api_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    user_id INTEGER NOT NULL,
    method TEXT NOT NULL,
    path TEXT NOT NULL,
    body TEXT,
    status_code INTEGER,
    response_summary TEXT
);

CREATE TABLE IF NOT EXISTS incident_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    incident_type TEXT NOT NULL,
    severity TEXT NOT NULL,
    description TEXT NOT NULL,
    detection_method TEXT NOT NULL,
    auto_fix_action TEXT,
    auto_fix_result TEXT,
    affected_entities TEXT,
    root_cause TEXT,
    suggestion TEXT,
    resolved_at TEXT,
    post_mortem_sent BOOLEAN DEFAULT 0
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_audit_timestamp ON ai_audit_log(timestamp);
CREATE INDEX IF NOT EXISTS idx_audit_trace ON ai_audit_log(trace_id);
CREATE INDEX IF NOT EXISTS idx_token_date ON token_usage(date);
CREATE INDEX IF NOT EXISTS idx_notification_ts ON notification_log(timestamp);
CREATE INDEX IF NOT EXISTS idx_notification_entity ON notification_log(entity_id);
CREATE INDEX IF NOT EXISTS idx_alert_ts ON alert_log(timestamp);
CREATE INDEX IF NOT EXISTS idx_alert_type ON alert_log(alert_type);
CREATE INDEX IF NOT EXISTS idx_context_user ON conversation_context(user_id, timestamp);
CREATE INDEX IF NOT EXISTS idx_cache_hash ON ai_cache(query_hash);
CREATE INDEX IF NOT EXISTS idx_undo_user ON undo_log(user_id, timestamp);
CREATE INDEX IF NOT EXISTS idx_raw_api_ts ON raw_api_log(timestamp);
CREATE INDEX IF NOT EXISTS idx_incident_ts ON incident_log(timestamp);
CREATE INDEX IF NOT EXISTS idx_incident_type ON incident_log(incident_type);
