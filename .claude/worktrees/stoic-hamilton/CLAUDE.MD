# CLAUDE.md — HA Copilot

> Full Home Assistant administration co-pilot via Telegram, powered by Claude AI.

---

## Project Identity

- **Name:** `ha-copilot`
- **Type:** Home Assistant Add-on (HA OS / Supervised)
- **Language:** Python 3.12 (all code, comments, docs in English)
- **License:** Apache 2.0
- **Repo:** GitHub — single repo with HA add-on structure
- **Target:** HA OS on Proxmox VM
- **Status:** Personal use first, open source (HACS) later

---

## What This Project Does

This is NOT a simple remote control. It is a **full HA administration assistant** that manages every aspect of a Home Assistant installation through Telegram:

1. **Device Control** — All device types, dynamic discovery, no hardcoded domains
2. **Automation CRUD** — Create/edit/delete automations via Claude-generated YAML
3. **Scene CRUD** — Create/edit/delete scenes from natural language
4. **Dashboard Management** — Lovelace view listing, view inspection, AI layout suggestions (card CRUD and AI reorganization deferred to Phase 8)
5. **Configuration Management** — Edit configuration.yaml, install/configure integrations, manage HA users
6. **Log Analysis** — Real-time logs from Core/Supervisor/OS/add-ons, AI-powered diagnosis
7. **Supervisor Management** — Add-on CRUD, restarts, backups, resource monitoring, update detection
8. **Alert Engine** — Configurable alerts with risk-scored auto-fix (watchdog + post-mortem in Fase 2)
9. **Proactive Notifications** — WebSocket event subscriptions with configurable filters
10. **Media** — Camera snapshots, voice commands (Claude audio), plotly history charts, YAML/config file exports
11. **AI Engine** — NL interpreter, YAML generator, log analyzer, dashboard suggester, language auto-detect, conversation memory
12. **Auth** — Multi-admin (config.yaml), private + group chat (configurable)
13. **Scheduled Commands** — NL time-based commands ("apagá en 30 min") as shortcuts to HA automations
14. **Raw API Mode** — Direct HA API calls for power users: `/raw POST /api/services/...`
15. **Template Tester** — Test Jinja2 HA templates from Telegram with real-time preview
16. **Snapshot & Diff** — Save entity state snapshots, compare changes (text diff)
17. **Energy Monitor** — Energy tracking with charts, anomaly alerts, consumption reports
18. **AI Documentation** — `/explain` any automation, entity, or integration in natural language
19. **Migration Assistant** — Detect deprecated integrations, obsolete YAML, upcoming breaking changes

---

## Engineering Ruleset — MANDATORY

Every file, commit, and decision MUST follow these rules. No exceptions unless explicitly noted.

### HARD RULE — Infrastructure Changes
Claude NEVER executes infrastructure changes autonomously. This includes terraform apply/destroy, scripts that modify infra, Docker operations (restart containers, clean volumes, docker-compose changes) regardless of environment. Claude prepares commands/scripts/plans and user always runs them manually. No exceptions.

### Rules

1. **Context & Alignment** — Update README.md after every structural/logic change. Log all design decisions in ADR.md with rationale, alternatives, and rollback strategy.

2. **Linux-First** — All paths/commands Linux-compatible. No PowerShell, no Windows binaries. Docker healthchecks on all dependencies. depends_on with condition: service_healthy. Drift Detection before any task.

3. **Secrets** — Zero hardcoding of secrets. New env vars auto-append to .env.example with comment. All vars structured for AWS Secrets Manager (`/app/env/VAR_NAME`).

4. **Resilience** — Exponential backoff (3 retries, 1s/2s/4s) on ALL external API calls (HA, Supervisor, Claude, Telegram). No generic `except Exception` — domain-specific error types only. Circuit breaker: 3 consecutive failures → circuit open → log critical.

5. **Observability** — All logs: JSON via structlog with timestamp, level, trace_id, context. Logs write to `/data/logs/`. Health Pulse every N minutes (configurable, default 5). Dead Man's Switch at M minutes (configurable, default 10) → sys.exit(1) + Supervisor watchdog restarts. trace_id propagates across all calls.

6. **Telegram Security** — Authorized user IDs from config.yaml `allowed_telegram_ids` list. Enforced at middleware level BEFORE any processing. ALL unauthorized attempts logged with source_id, username, timestamp. Works in private chat, groups, or both (configurable `chat_mode`).

7. **AI & Claude** — Log token consumption (input_tokens, output_tokens, model) per request. Explicit max_tokens on every call — never defaults. Prompts versioned in `/data/prompts/` — never inline. Responses validated against Pydantic schema. Fallback: retry 3x → cache → alert. Prompt Regression Guard with golden pairs. AI Decision Audit Log: raw prompt + raw response + final action.

8. **Testing** — pytest + pytest-asyncio + pytest-aiohttp. Every new service/handler/parser: min 1 unit + 1 integration test. Tests run in Docker.

9. **Schema-First** — Define Pydantic model BEFORE writing any module. Claude response schemas in `app/schemas/`.

10. **Versioning** — Breaking changes require new version. CHANGELOG.md in Keep a Changelog format.

11. **Cost** — Every external API feature declares estimated cost in ADR. Alert if actual > 2x estimate. Token budget system with configurable daily limit.

12. **Deployment** — deploy.md is single source of truth. Contains: provisioning, validation, maintenance, rollback.

13. **Workflow** — Plan mode for 3+ steps or 2+ modules. Log lessons in ADR.md after corrections. Verify before done (tests + logs + evidence). Pause for elegance on 50+ lines or 2+ modules.

14. **Task Management** — Simplicity first, root cause only, minimum impact.

15. **Dependencies** — All packages pinned to exact version. Monthly review.

16. **Commits** — Descriptive messages, no formal standard required.

---

## Architecture

```
┌──────────────────────────────────────────────────────────────┐
│                   Home Assistant OS (Proxmox VM)             │
│                                                              │
│  ┌──────────────┐     ┌───────────────────────────────────┐  │
│  │  HA Core     │     │  ha-copilot (add-on)              │  │
│  │  REST API    │◄────┤                                   │  │
│  │  WebSocket   │◄────┤  Telegram Bot (polling/webhook)   │  │
│  └──────────────┘     │       │                           │  │
│  ┌──────────────┐     │  Auth Middleware (ID allowlist)    │  │
│  │  Supervisor  │     │       │                           │  │
│  │  API         │◄────┤  Command Router                   │  │
│  └──────────────┘     │    ├─ /cmd → Module Handler       │  │
│                       │    └─ NL/voice → Claude AI         │  │
│                       │       │                           │  │
│                       │  Modules                          │  │
│                       │    ├─ DeviceController             │  │
│                       │    ├─ AutomationCRUD               │  │
│                       │    ├─ SceneCRUD                    │  │
│                       │    ├─ DashboardManager             │  │
│                       │    ├─ ConfigManager                │  │
│                       │    ├─ LogAnalyzer                  │  │
│                       │    ├─ SupervisorManager            │  │
│                       │    ├─ AlertEngine                  │  │
│                       │    ├─ MediaHandler                 │  │
│                       │    └─ EntityManager                │  │
│                       │       │                           │  │
│                       │  HA Client Layer                   │  │
│                       │    ├─ REST (aiohttp)               │  │
│                       │    ├─ WebSocket (persistent)       │  │
│                       │    └─ Supervisor Client            │  │
│                       │       │                           │  │
│                       │  Event Listener → Notifications    │  │
│                       │  Alert Engine → Auto-fix           │  │
│                       │  Claude AI Engine                  │  │
│                       │    ├─ NL Interpreter               │  │
│                       │    ├─ YAML Generator               │  │
│                       │    ├─ Log Analyzer                 │  │
│                       │    ├─ Dashboard Suggester          │  │
│                       │    └─ Voice (audio → text)         │  │
│                       │                                   │  │
│                       │  SQLite DB (/data/ha_copilot.db)  │  │
│                       │  Logs (/data/logs/)               │  │
│                       │  Prompts (/data/prompts/)         │  │
│                       └───────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────┘
         │                          │
  ┌──────▼──────┐            ┌──────▼──────┐
  │  Telegram   │            │  Claude API │
  │  Bot API    │            │  (Anthropic)│
  └─────────────┘            └─────────────┘
```

### API Access

| API | URL | Auth | Purpose |
|-----|-----|------|---------|
| HA Core REST | `http://supervisor/core/api` | `$SUPERVISOR_TOKEN` | Entity control, services, config, history |
| HA WebSocket | `ws://supervisor/core/websocket` | `$SUPERVISOR_TOKEN` | Real-time events, Lovelace config |
| Supervisor | `http://supervisor/` | `$SUPERVISOR_TOKEN` | System info, add-ons, backups, host, OS, logs |
| HA Config | `http://supervisor/core/api/config/*` | `$SUPERVISOR_TOKEN` | Automation/scene CRUD |

`$SUPERVISOR_TOKEN` is auto-injected by Supervisor. Never store, log, or hardcode it.

---

## Tech Stack

| Component | Choice | Reason |
|-----------|--------|--------|
| Language | Python 3.12 | HA ecosystem, Claude SDK, I/O-bound project |
| Async | asyncio + aiohttp | Standard, mature |
| Telegram | python-telegram-bot 21.x | Mature, async, polling + webhook |
| AI | anthropic SDK | Official, async |
| Schemas | Pydantic v2 | Schema-first, fast validation |
| Database | SQLite via aiosqlite | Zero config, included in HA backups |
| YAML | ruamel.yaml | Preserves comments (critical for config editing) |
| Logging | structlog | Structured JSON output |
| JSON | orjson | Fast serialization |
| Charts | plotly + kaleido | PNG export for Telegram |
| Testing | pytest + pytest-asyncio | Standard, mature |
| Base image | ghcr.io/home-assistant/*-base-python:3.12-alpine3.19 | Official HA images |

### Pinned Dependencies

```
python-telegram-bot==21.9
anthropic==0.52.0
aiohttp==3.11.11
pydantic==2.10.4
aiosqlite==0.20.0
ruamel.yaml==0.18.6
structlog==24.4.0
orjson==3.10.13
plotly==5.24.1
kaleido==0.2.1
pytest==8.3.4
pytest-asyncio==0.24.0
pytest-aiohttp==1.0.5
```

---

## Repository Structure

```
ha-copilot/
├── config.yaml                     # HA add-on metadata
├── build.yaml                      # Multi-arch build config
├── Dockerfile                      # Container definition
├── run.sh                          # Container entrypoint
├── CHANGELOG.md                    # Keep a Changelog format
├── DOCS.md                         # User-facing documentation
├── README.md                       # Repo README
├── LICENSE                         # Apache 2.0
├── deploy.md                       # Single source of truth for deployment
├── ADR.md                          # Architecture Decision Records
├── requirements.txt                # Pinned Python deps
├── requirements-dev.txt            # Dev/test deps
├── .env.example                    # Required env vars template
├── icon.png                        # 128x128 add-on icon
├── logo.png                        # 256x256 add-on logo
├── translations/
│   └── en.yaml                     # Config option translations
├── app/
│   ├── __init__.py
│   ├── main.py                     # Entrypoint, async orchestrator
│   ├── config.py                   # Settings loader from /data/options.json
│   ├── database.py                 # SQLite setup, migrations, maintenance
│   ├── middleware/
│   │   ├── __init__.py
│   │   └── auth.py                 # Telegram ID allowlist enforcement
│   ├── bot/
│   │   ├── __init__.py
│   │   ├── handler.py              # Bot setup, command routing
│   │   ├── callbacks.py            # Inline keyboard callback handlers
│   │   ├── formatters.py           # Message formatting (MarkdownV2)
│   │   └── pagination.py           # Inline keyboard pagination for long lists
│   ├── core/
│   │   ├── __init__.py
│   │   ├── module_base.py          # Base class for all modules (ModuleBase ABC)
│   │   ├── module_registry.py      # Explicit module registration + lifecycle
│   │   ├── command_queue.py        # FIFO idempotent command queue per user
│   │   ├── degradation.py          # Graceful degradation map + component health
│   │   └── self_test.py            # Startup self-test: all services health check
│   ├── modules/                    # Each module is a plugin (implements PluginBase)
│   │   ├── __init__.py
│   │   ├── devices.py              # Device control (all domains, dynamic)
│   │   ├── automations.py          # Automation CRUD
│   │   ├── scenes.py               # Scene CRUD
│   │   ├── dashboards.py           # Dashboard/Lovelace management
│   │   ├── config_manager.py       # configuration.yaml, integrations, users
│   │   ├── log_analyzer.py         # Log reading + AI analysis
│   │   ├── supervisor_mgr.py       # Add-ons, backups, restarts, resources
│   │   ├── system.py               # System monitoring, daily digest
│   │   ├── entities.py             # Entity management, history, aliases
│   │   ├── quick_actions.py        # User-defined shortcuts
│   │   ├── scheduler.py            # NL scheduled commands → HA automations
│   │   ├── raw_api.py              # Direct HA API calls for power users
│   │   ├── template_tester.py      # Jinja2 template testing with live preview
│   │   ├── snapshots.py            # Entity state snapshots + text diff
│   │   ├── energy.py               # Energy tracking, charts, anomaly alerts
│   │   ├── explain.py              # AI documentation for entities/automations
│   │   └── migration.py            # Migration assistant: deprecated, obsolete, breaking changes
│   ├── ai/
│   │   ├── __init__.py
│   │   ├── engine.py               # Claude API, fallback chain, token tracking
│   │   ├── mapper.py               # AI response → HA action mapper
│   │   ├── yaml_generator.py       # Automation/scene/dashboard YAML gen
│   │   ├── context.py              # Progressive context loading
│   │   ├── conversation.py         # Conversation memory (configurable)
│   │   └── audit.py                # AI Decision Audit Log
│   ├── ha/
│   │   ├── __init__.py
│   │   ├── client.py               # HA REST API client (aiohttp, backoff)
│   │   ├── supervisor.py           # Supervisor API client
│   │   ├── websocket.py            # Persistent WS client, auto-reconnect
│   │   └── discovery.py            # Dynamic domain/entity/service discovery
│   ├── events/
│   │   ├── __init__.py
│   │   ├── listener.py             # WS event subscription manager
│   │   ├── filters.py              # Configurable event filters + cooldown
│   │   └── notifier.py             # Proactive notification sender
│   ├── alerts/
│   │   ├── __init__.py
│   │   ├── engine.py               # Health check runner, alert dispatcher
│   │   ├── conditions.py           # Configurable alert conditions (device_unavailable, low_battery, disk_usage)
│   │   ├── auto_fix.py             # Risk-scored auto-remediation (risk 1-2 implemented; 3-5 in Fase 2)
│   │   └── digest.py               # Daily health digest
│   ├── media/
│   │   ├── __init__.py
│   │   ├── camera.py               # Camera snapshot handler
│   │   ├── voice.py                # Audio → Claude transcription
│   │   ├── charts.py               # Plotly history charts → PNG
│   │   └── export.py               # YAML/config/backup file export
│   ├── schemas/
│   │   ├── __init__.py
│   │   ├── ai_action.py            # AIAction, AIResponse
│   │   ├── device_command.py        # DeviceCommand, DeviceState
│   │   ├── automation_schema.py     # AutomationConfig validation
│   │   ├── scene_schema.py          # SceneConfig validation
│   │   ├── dashboard_schema.py      # Lovelace card/view validation
│   │   ├── event_subscription.py    # EventSubscription config
│   │   ├── alert_config.py          # AlertCondition, AutoFixLevel
│   │   ├── energy_schema.py         # EnergyReport, AnomalyAlert
│   │   ├── snapshot_schema.py       # EntitySnapshot, SnapshotDiff
│   │   └── system_query.py          # SystemMetrics, SystemInfo
│   ├── undo/
│   │   ├── __init__.py
│   │   └── manager.py              # Undo system for destructive actions
│   └── observability/
│       ├── __init__.py
│       ├── logger.py               # structlog JSON setup
│       └── health.py               # Health Pulse + Dead Man's Switch
├── prompts/
│   ├── v1/
│   │   ├── system.txt              # Main NL interpreter prompt
│   │   ├── automation_creator.txt  # Automation YAML gen prompt
│   │   ├── scene_creator.txt       # Scene YAML gen prompt
│   │   ├── dashboard_creator.txt   # Dashboard YAML gen prompt
│   │   ├── log_analyzer.txt        # Log diagnosis prompt
│   │   ├── explainer.txt           # AI documentation prompt
│   │   └── migration_checker.txt   # Migration analysis prompt
│   └── golden/
│       └── regression_tests.json   # Prompt Regression Guard pairs
├── migrations/
│   ├── 001_initial.sql             # Initial schema
│   ├── 002_snapshots.sql           # Snapshots table
│   └── README.md                   # Migration conventions
└── tests/
    ├── conftest.py                 # Shared fixtures
    ├── fixtures/
    │   └── options.json            # Mock config for testing
    ├── unit/
    │   ├── test_auth.py
    │   ├── test_schemas.py
    │   ├── test_devices.py
    │   ├── test_ai_mapper.py
    │   ├── test_automations.py
    │   ├── test_config_manager.py
    │   ├── test_conversation.py
    │   ├── test_dashboards.py
    │   ├── test_degradation.py
    │   ├── test_energy.py
    │   ├── test_event_filters.py
    │   ├── test_explain.py
    │   ├── test_auto_fix.py
    │   ├── test_command_queue.py
    │   ├── test_log_analyzer.py
    │   ├── test_media.py
    │   ├── test_migration.py
    │   ├── test_module_registry.py
    │   ├── test_quick_actions.py
    │   ├── test_self_test.py
    │   ├── test_snapshots.py
    │   ├── test_supervisor_mgr.py
    │   └── test_system.py
    └── integration/
        └── __init__.py
```

---

## Add-on Configuration (config.yaml)

```yaml
name: "HA Copilot"
version: "0.1.0"
slug: "ha-copilot"
description: >-
  Full Home Assistant administration co-pilot via Telegram.
  AI-powered natural language control, automation CRUD,
  dashboard management, log analysis, proactive alerts,
  and system monitoring.
url: "https://github.com/pedro/ha-copilot"
arch:
  - amd64
  - aarch64
  - armv7
startup: application
boot: auto
init: false
watchdog: "tcp://[HOST]:[PORT:8099]"

hassio_api: true
hassio_role: "admin"
homeassistant_api: true
auth_api: true

host_network: false

map:
  - type: data
    path: /data
  - type: homeassistant_config
    read_only: false

options:
  # --- Telegram ---
  telegram_bot_token: ""
  allowed_telegram_ids:
    - 0
  chat_mode: "both"
  telegram_mode: "polling"
  allowed_group_ids: []
  notification_target: "private"

  # --- AI ---
  anthropic_api_key: ""
  ai_enabled: true
  ai_model: "claude-sonnet-4-20250514"
  ai_max_tokens: 1024
  ai_daily_token_budget: 500000
  ai_conversation_memory: true
  ai_conversation_ttl_minutes: 30
  ai_conversation_max_messages: 10

  # --- System ---
  log_level: "info"
  health_pulse_interval_seconds: 300
  dead_man_switch_timeout_seconds: 600
  health_check_interval_seconds: 300
  daily_digest_enabled: true
  daily_digest_time: "08:00"
  db_purge_days: 90

  # --- Alerts ---
  alert_conditions:
    - type: "device_unavailable"
      enabled: true
      cooldown_seconds: 300
    - type: "low_battery"
      enabled: true
      threshold: 20
      cooldown_seconds: 3600
    - type: "disk_usage"
      enabled: true
      threshold_percent: 85
      cooldown_seconds: 3600
    - type: "integration_error"
      enabled: true
      cooldown_seconds: 600
    - type: "automation_failed"
      enabled: true
      cooldown_seconds: 300
    - type: "critical_log"
      enabled: true
      cooldown_seconds: 60
  auto_fix_max_risk_score: 1

  # --- Notifications ---
  proactive_notifications: true
  notification_events:
    - "state_changed"
    - "automation_triggered"
  notification_domains:
    - "binary_sensor"
    - "alarm_control_panel"
  notification_entity_patterns: []

  # --- Entity Aliases ---
  entity_aliases: {}

  # --- Quick Actions ---
  quick_actions: []

  # --- Confirmation Levels ---
  confirmation_levels:
    none:
      - "get_state"
      - "list_entities"
      - "system_info"
    single_click:
      - "call_service_single"
      - "toggle_automation"
      - "activate_scene"
    double_confirm:
      - "call_service_multi"
      - "create_automation"
      - "edit_automation"
      - "create_scene"
      - "edit_configuration"
    password:
      - "delete_automation"
      - "delete_scene"
      - "restart_core"
      - "restore_backup"
      - "manage_users"
      - "host_reboot"

schema:
  telegram_bot_token: "str"
  allowed_telegram_ids:
    - "int"
  chat_mode: "list(private|group|both)"
  telegram_mode: "list(polling|webhook)"
  allowed_group_ids:
    - "int?"
  notification_target: "list(private|group|both)"
  anthropic_api_key: "str"
  ai_enabled: "bool"
  ai_model: "str"
  ai_max_tokens: "int(256,8192)"
  ai_daily_token_budget: "int(10000,5000000)"
  ai_conversation_memory: "bool"
  ai_conversation_ttl_minutes: "int(5,1440)"
  ai_conversation_max_messages: "int(2,50)"
  log_level: "list(debug|info|warning|error)"
  health_pulse_interval_seconds: "int(60,900)"
  dead_man_switch_timeout_seconds: "int(120,1800)"
  health_check_interval_seconds: "int(60,3600)"
  daily_digest_enabled: "bool"
  daily_digest_time: "str"
  db_purge_days: "int(7,365)"
  alert_conditions:
    - type: "str"
      enabled: "bool"
      cooldown_seconds: "int?"
      threshold: "float?"
      threshold_percent: "float?"
  auto_fix_max_risk_score: "int(0,5)"
  proactive_notifications: "bool"
  notification_events:
    - "str"
  notification_domains:
    - "str"
  notification_entity_patterns:
    - "str?"
  entity_aliases: {}
  quick_actions:
    - name: "str"
      actions:
        - service: "str"
          target: {}
  confirmation_levels: {}
```

---

## Database — SQLite

File: `/data/ha_copilot.db`

### Schema (migrations/001_initial.sql)

```sql
CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

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

CREATE TABLE IF NOT EXISTS entity_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    timestamp TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    user_id INTEGER NOT NULL,
    states TEXT NOT NULL,
    entity_count INTEGER NOT NULL
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
CREATE INDEX IF NOT EXISTS idx_snapshot_name ON entity_snapshots(name);
CREATE INDEX IF NOT EXISTS idx_raw_api_ts ON raw_api_log(timestamp);
CREATE INDEX IF NOT EXISTS idx_incident_ts ON incident_log(timestamp);
CREATE INDEX IF NOT EXISTS idx_incident_type ON incident_log(incident_type);
```

### Maintenance (automatic)
- Purge audit/notification/alert logs older than `db_purge_days` (default 90)
- Purge conversation context older than `ai_conversation_ttl_minutes`
- Purge expired cache entries hourly
- Purge expired undo entries hourly
- VACUUM weekly
- Monitor DB size → alert if > 500MB (configurable)

---

## Key Design Patterns

### Progressive Context Loading (reduces Claude tokens ~40-60%)
Do NOT send all entities to Claude in every request. Instead:
1. First pass: send domain list + entity counts → Claude identifies needed domains
2. Second pass: send only entities from relevant domains
3. Cache entity list in memory with WS-driven invalidation (state_changed → update only that entity)
4. Fallback: 5-min TTL if WS disconnects

### Conversation Memory (configurable)
When enabled, send last N messages (default 10) or messages within TTL (default 30 min) as conversation history to Claude. This allows Claude to resolve references like "bajala al 30%" after "prendé la luz de la sala". Store in SQLite `conversation_context` table. Purge automatically.

### Entity Alias System
Users define aliases in config.yaml `entity_aliases`. Claude receives aliases as additional context for better NL mapping. Example: `"luz sala": "light.living_room_main"`.

### Smart Rate Limiting for Claude
- Structured commands (/lights, /sys) → no Claude, no rate limit
- NL simple (device control) → Claude with aggressive cache (same query in 5 min → cache)
- NL complex (create automation) → Claude, no cache, but token budget applies
- Token budget: configurable daily limit, alert at 80%, soft-block at 100%

### Dry-Run for CRUD Operations
Before creating/editing automation, scene, or config:
1. Claude generates YAML
2. Validate with Pydantic schema (exception: dashboard/Lovelace YAML — schema too open-ended, no Pydantic validation)
3. Validate with HA config check API when available
4. Show preview to user in Telegram
5. Create automatic backup
6. Apply only after user confirmation

### Risk-Scored Auto-Fix
Each auto-fix action has a risk score (1-5):
- 1 (trivial): restart crashed add-on, clear temp files
- 2 (low): reload integration, clear cache
- 3 (medium): reinstall add-on, revert single config change
- 4 (high): restart HA Core
- 5 (critical): restore backup, host reboot

User configures `auto_fix_max_risk_score` (default 1). Actions above threshold require user confirmation. ALL auto-fixes create backup first and log to AI Audit Log.

### Undo System
Destructive actions (delete, edit config) save previous state to `undo_log` with configurable TTL (default 10 min). User can `/undo` to revert. Only the most recent action per entity is undoable.

### Confirmation Levels (configurable)
- `none` — execute immediately (read operations)
- `single_click` — one tap ✅ (single entity control)
- `double_confirm` — preview + "Are you sure?" (multi-entity, CRUD)
- `password` — requires PIN code (destructive, system-level)

### Connection Pooling
Single `aiohttp.ClientSession` for the entire add-on lifecycle. Reuse TCP connections. Never create/destroy per request.

### Entity Cache with WS Invalidation
In-memory cache of all entities. WebSocket `state_changed` events update only the changed entity. ~90% reduction in HA API calls vs polling.

### Lazy Module Loading
Always load at startup: auth, bot, ha_client, websocket, health, database, plugin_registry.
Lazy load on first use: dashboard_manager, log_analyzer, media_handler, config_manager, energy, migration.

### Module System (Clean Interface, No Plugin Framework)
Every module implements `ModuleBase` with a consistent interface:
```python
class ModuleBase(ABC):
    name: str                    # Unique module identifier
    description: str             # Human-readable description
    commands: list[str]          # Telegram commands this module handles
    
    @abstractmethod
    async def setup(self, app: AppContext) -> None: ...
    
    @abstractmethod
    async def teardown(self) -> None: ...
    
    @abstractmethod
    async def handle_command(self, cmd: str, args: list, context: CommandContext) -> None: ...
```
- All modules in `app/modules/` implement `ModuleBase`
- Modules registered explicitly in `main.py` — no auto-discovery, no plugin framework
- This keeps complexity minimal while maintaining clean separation
- To disable a module: comment it out from the registration list in `main.py`
- Future plugin system: when open source and community needs it, refactor registration from explicit to dynamic — modules don't change at all

### Idempotent Command Queue
Messages from same user processed sequentially via async FIFO queue:
- Prevents race conditions ("prendé la sala" + "bajala al 50%" processed in order)
- Each command gets a trace_id assigned at queue entry
- Queue timeout: 30s per command (configurable), then skip + alert
- Queue depth limit: 10 commands (configurable), reject with "🔴 Too many pending commands"
- Different users have independent queues (parallel processing between users)

### Graceful Degradation Map
Explicit behavior when each component fails:

| Component | Failure Mode | Degraded Behavior |
|-----------|-------------|-------------------|
| Claude API | Unreachable | Structured commands work. NL disabled. Alert user once. |
| WebSocket | Disconnected | Proactive notifications paused. Polling fallback for critical alerts. Entity cache uses TTL. |
| SQLite | Corrupted | Recreate empty DB. Alert user. Audit log lost (acceptable). |
| HA REST API | Unreachable | All commands fail. Retry with backoff. Alert after 3 failures. |
| Supervisor API | Unreachable | System/addon commands fail. Device control still works via HA API. |
| Telegram API | Unreachable | Queue outbound messages. Retry. Log locally. |

Each component has a health state tracked by `degradation.py`: `healthy`, `degraded`, `unavailable`. Startup self-test sets initial state. WebSocket events and periodic checks update state. `/sys` shows component health.

### Startup Self-Test
On add-on start, before accepting Telegram commands:
1. Check HA REST API reachable → set ha_api state
2. Check Supervisor API reachable → set supervisor_api state
3. Check WebSocket connectable → set websocket state
4. Check Telegram token valid (getMe) → set telegram state
5. Check Claude API key valid (models list) → set claude state
6. Check SQLite writable → set database state
7. Send startup report to all allowed Telegram IDs:
```
🟢 HA Copilot v0.1.0 online
├ 🟢 HA API: connected (HA 2026.3.4)
├ 🟢 Supervisor: connected
├ 🟢 WebSocket: connected
├ 🟢 Telegram: authenticated
├ 🟢 Claude API: authenticated (sonnet-4)
├ 🟢 Database: /data/ha_copilot.db (2.3 MB)
└ 📊 45 entities across 8 domains
```
If any component fails, startup continues in degraded mode (never block boot).

### Scheduled Commands → HA Automations
When user says "apagá las luces en 30 minutos", Claude interprets as a scheduled command. Instead of an internal scheduler, create a one-shot HA automation:
- Claude generates automation YAML with `trigger: time` set to now + offset
- Automation created via HA Config API with tag `ha_copilot_scheduled`
- After execution, automation auto-disables or deletes (configurable)
- `/schedule list` shows pending scheduled commands
- `/schedule cancel <id>` cancels a scheduled command

### Self-Healing Watchdog *(Fase 2 — not yet implemented)*
Beyond risk-scored auto-fix, a background watchdog that detects:
- **Stale integrations**: entity hasn't updated in N minutes (configurable per domain) → alert + optional restart
- **Entity leaks**: entity count for a domain growing abnormally (>20% increase in 24h) → alert
- **Post-mortem reports**: after any incident (auto-fix, crash, alert), generate a summary:
  ```
  📋 Post-Mortem: Add-on zigbee2mqtt crash
  ├ Detected: 14:32 UTC
  ├ Auto-fix: restart add-on (risk score 1)
  ├ Result: ✅ recovered in 45s
  ├ Affected entities: 14 zigbee devices
  ├ Root cause: Memory limit exceeded (512MB)
  └ Suggestion: Increase memory limit or reduce device count
  ```
- Post-mortem stored in `alert_log` with full context

### Energy Monitor
- Discover all `sensor` entities with `device_class: energy` or `device_class: power`
- `/energy today` — daily consumption summary with plotly chart
- `/energy week` / `/energy month` — period reports
- `/energy compare` — compare current vs previous period
- Anomaly detection: if consumption > 2x rolling average → proactive alert
- Cost estimation if user configures electricity rate in config.yaml

### Migration Assistant
On demand (`/migrate check`) or as part of daily digest:
- Query HA release notes API for upcoming breaking changes
- Compare installed integration versions against known deprecations
- Detect YAML config that should be migrated to UI-based config
- Claude analyzes configuration.yaml for obsolete patterns
- Output: prioritized list of recommended actions

### AI Documentation (/explain)
- `/explain auto <name>` — Claude reads automation YAML and explains in natural language: what triggers it, conditions, actions, edge cases
- `/explain entity <entity_id>` — Claude explains: what integration provides it, what it measures, where it's used in automations/dashboards
- `/explain integration <name>` — Claude explains what the integration does, its entities, common issues
- Uses progressive context: fetches only the relevant config/state for the explanation

### Raw API Mode
- `/raw GET /api/states/light.sala` — direct GET request
- `/raw POST /api/services/light/turn_on {"entity_id": "light.sala"}` — direct POST
- `/raw SUP GET /supervisor/info` — direct Supervisor API call
- Response shown as formatted JSON in Telegram
- Logged to audit log (not AI audit, separate `raw_api_log`)
- Confirmation required for POST/PUT/DELETE (configurable)

### Template Tester
- `/template {{ states("sensor.temp") }}` — evaluate and return result
- `/template watch {{ states("sensor.temp") }}` — re-evaluate every 5s for 60s, update message in-place
- Uses HA REST API `POST /api/template` endpoint
- Useful for debugging automation templates before deploying

---

## Telegram Bot — Commands

| Command | Module | Description |
|---------|--------|-------------|
| `/start` | bot | Welcome + onboarding wizard (S11) on first run |
| `/help` | bot | Full command reference |
| `/quick` | quick_actions | Show user-defined quick action buttons |
| `/devices [domain]` | devices | List/control devices with inline keyboards |
| `/status <entity>` | entities | Entity state + attributes |
| `/entities [domain]` | entities | List entities with pagination (S12) |
| `/history <entity> [hours]` | entities | State history, optionally as chart |
| `/auto` | automations | List automations |
| `/auto <id> on\|off` | automations | Enable/disable |
| `/auto <id> trigger` | automations | Manual trigger |
| `/auto <id> show` | automations | Show YAML |
| `/auto <id> delete` | automations | Delete (with confirmation) |
| `/scenes` | scenes | List scenes |
| `/scene <id> activate` | scenes | Activate |
| `/scene <id> delete` | scenes | Delete (with confirmation) |
| `/dash` | dashboards | List dashboards |
| `/dash <name> show` | dashboards | Show dashboard config |
| `/dash suggest` | dashboards | AI suggests layout based on devices |
| `/config show` | config_manager | Show configuration.yaml |
| `/config check` | config_manager | Validate config |
| `/integrations` | config_manager | List integrations |
| `/users` | config_manager | List HA users |
| `/logs [source] [level]` | log_analyzer | Read logs (core/supervisor/addon) |
| `/logs analyze` | log_analyzer | AI analyzes recent errors |
| `/sys` | system | System health dashboard |
| `/addons` | supervisor_mgr | List add-ons + status |
| `/addon <slug> restart` | supervisor_mgr | Restart specific add-on |
| `/backup create` | supervisor_mgr | Create full backup |
| `/backup list` | supervisor_mgr | List available backups |
| `/camera <name>` | media | Camera snapshot |
| `/chart <entity> [hours]` | media | Plotly history chart |
| `/export <type>` | media | Export automations/scenes/config YAML |
| `/notify on\|off` | events | Toggle proactive notifications |
| `/subs` | events | List active event subscriptions |
| `/alerts` | alerts | Show active/recent alerts |
| `/audit export [days]` | audit | Export AI audit log |
| `/audit stats` | audit | AI usage summary |
| `/audit cost` | audit | Monthly cost |
| `/undo` | undo | Revert last destructive action |
| `/restart core\|supervisor` | supervisor_mgr | Restart (with confirmation) |
| `/reboot` | supervisor_mgr | Host reboot (with PIN) |
| `/raw <method> <path> [body]` | raw_api | Direct HA/Supervisor API call |
| `/template <jinja2>` | template_tester | Evaluate Jinja2 template |
| `/template watch <jinja2>` | template_tester | Live template preview (updates in-place) |
| `/snapshot save [name]` | snapshots | Save current entity states |
| `/snapshot diff [name]` | snapshots | Text diff against saved snapshot |
| `/snapshot list` | snapshots | List saved snapshots |
| `/energy today\|week\|month` | energy | Energy consumption report + chart |
| `/energy compare` | energy | Compare vs previous period |
| `/explain auto <id>` | explain | AI explains automation in natural language |
| `/explain entity <id>` | explain | AI explains entity: source, usage, automations |
| `/explain integration <n>` | explain | AI explains integration |
| `/migrate check` | migration | Check for deprecated/obsolete configs |
| `/schedule list` | scheduler | List pending scheduled commands |
| `/schedule cancel <id>` | scheduler | Cancel scheduled command |
| *Free text* | ai.engine | Claude NL → structured action |
| *Voice message* | media.voice | Audio → Claude → action |

---

## Telegram Bot — Modes

### Polling (default)
- Simple, no external URL needed, works behind NAT/firewall
- Set `telegram_mode: "polling"` in config

### Webhook
- More efficient, instant delivery, lower latency
- Requires URL reachable by Telegram (e.g., via Cloudflare tunnel or port forward)
- Set `telegram_mode: "webhook"` in config
- Webhook URL served on internal ingress port (8099)
- HA Supervisor ingress handles external routing

---

## Error Handling

### Domain-Specific Exceptions

```python
class HACopilotError(Exception): ...
class AuthorizationError(HACopilotError): ...
class EntityNotFoundError(HACopilotError): ...
class AIParsingError(HACopilotError): ...
class AIServiceUnavailableError(HACopilotError): ...
class AIBudgetExceededError(HACopilotError): ...
class HAConnectionError(HACopilotError): ...
class HAAuthError(HACopilotError): ...
class ServiceCallError(HACopilotError): ...
class AutomationValidationError(HACopilotError): ...
class WebSocketError(HACopilotError): ...
class ConfigValidationError(HACopilotError): ...
class UndoExpiredError(HACopilotError): ...
```

### Claude API Fallback Chain
1. Call → success → validate schema → execute
2. Retry (2s) → success → validate → execute
3. Retry (4s) → success → validate → execute
4. All retries failed → check cache
5. Cache hit → return + warning "⚠️ Using cached response"
6. Cache miss → "🔴 AI unavailable. Use /help for structured commands."

### WebSocket Recovery
1. Connection lost → log error
2. Wait 5s → reconnect + re-auth
3. Re-subscribe to all event types
4. 3 consecutive failures → log critical, continue without proactive notifications
5. Background retry every 60s

---

## Implementation Phases

All 20 modules are MVP. Phases ordered so you have a usable bot by Week 4.

**Confirmed scope per module:**
- Automation CRUD: simple automations only (1 trigger, 1 action, no choose/repeat/parallel)
- Alert Engine: configurable alerts + risk-scored auto-fix risk 1-2 only; watchdog/post-mortem/conditions integration_error|automation_failed|critical_log deferred to Fase 2
- Config Manager: read-only (show + check), integrations list, users list — configuration.yaml editing deferred to Phase 8
- Dashboard Manager: list views + show + AI suggest — card CRUD, AI reorganize deferred to Phase 8

### Phase 1: Foundation (Week 1-2) ✅ DONE — v0.1.0 (2026-03-23)
**Goal: add-on boots, bot responds, infrastructure solid.**
- Add-on skeleton: config.yaml, build.yaml, Dockerfile, run.sh
- ModuleBase ABC + explicit module registration in main.py
- Pydantic schemas (all modules — schema-first)
- SQLite database setup + migrations (all tables)
- HA REST client with exponential backoff (3 retries)
- Supervisor API client
- structlog JSON logging → /data/logs/
- Auth middleware (allowlist from config.yaml, group support)
- Telegram bot: polling + webhook modes, /start, /help
- Idempotent command queue (FIFO per user)
- Health Pulse + Dead Man's Switch
- Graceful degradation map + component health tracking
- Startup self-test → Telegram report (all services)
- deploy.md, ADR.md, CHANGELOG.md, README.md
- Unit tests: auth, schemas, db, API client, command queue, self-test
- **Milestone: bot responds to /start and /help, self-test passes**

### Phase 2: Device Control + AI Engine (Week 3-4) ✅ DONE — v0.2.0 (2026-03-23)
**Goal: control any device via NL from Telegram.**
- Dynamic domain/entity/service discovery
- WebSocket client (persistent, auto-reconnect)
- Entity cache with WS-driven invalidation
- /devices [domain] with inline keyboards + pagination
- /status <entity>, /entities [domain], /history <entity>
- Claude AI engine with versioned prompts
- Progressive context loading (domain list → relevant entities)
- Conversation memory (configurable on/off, TTL, max messages)
- Entity alias system (config.yaml mapping)
- NL → AIAction mapper with Pydantic validation
- AI Decision Audit Log + token consumption tracking
- Confirmation flow (inline keyboards, configurable levels)
- Claude fallback chain: retry → cache → alert
- Language auto-detection
- Smart rate limiting + daily token budget
- Prompt Regression Guard with golden pairs
- Unit + integration tests
- **Milestone: "prendé la luz de la sala" works end-to-end**

### Phase 3: System Admin + Power Tools (Week 5-6) ✅ DONE — v0.3.0 (2026-03-23)
**Goal: full system management from Telegram.**
- /sys — system dashboard with component health status
- /addons — list, restart, install, update, uninstall
- /restart core|supervisor, /reboot with confirmation levels
- /backup create, /backup list, download backup via Telegram (handle >50MB)
- /logs [source] [level] — Core, Supervisor, OS, add-on logs
- /logs analyze — Claude AI diagnosis of recent errors
- Resource monitoring per add-on (CPU, RAM via stats API)
- Outdated add-on detection → notification
- Daily health digest (configurable time, Telegram message)
- /raw <method> <path> [body] — direct HA/Supervisor API calls
- /template <jinja2> — evaluate + /template watch for live preview
- Integration tests
- **Milestone: full sysadmin from phone**

### Phase 4: Automation/Scene CRUD + Scheduling (Week 7-8) ✅ DONE — v0.4.0 (2026-03-23)
**Goal: create and manage automations from NL.**
- /auto — list, enable/disable, trigger, show YAML
- /auto create via Claude (simple: 1 trigger + 1 action)
- /auto <id> delete with confirmation
- /scenes — list, activate, create, delete
- Claude YAML generator prompts (automation + scene)
- Dry-run validation: Pydantic → HA config check API → preview → confirm
- Undo system (/undo with TTL)
- Auto-backup before any CRUD operation
- Scheduled commands: "apagá en 30 min" → one-shot HA automation
- /schedule list, /schedule cancel
- /explain auto <id>, /explain entity <id>, /explain integration (AI docs)
- Integration tests
- **Milestone: "creá una automatización que prenda la luz cuando abra la puerta" works**

### Phase 5: Proactive Alerts + Notifications (Week 9-10) ✅ DONE — v0.5.0 (2026-03-23)
**Goal: bot proactively alerts you of problems and fixes trivial ones.**
- Event subscription system via WebSocket
- Configurable event filters (domain, entity pattern, state, cooldown)
- Notification target routing (private/group/both, configurable per rule)
- Alert engine with configurable conditions (device offline, battery low, disk full, etc.)
- Risk-scored auto-fix (1-5 scale, configurable max level)
- Auto-backup before any auto-fix
- All auto-fixes logged to AI Audit Log
- /notify on|off, /subs, /alerts commands
- Integration tests
- **Milestone: "🚪 Puerta garage abierta" arrives without asking**

### Phase 6: Config + Dashboard Management (Week 11-12) ✅ DONE — v0.6.0 (2026-03-24)
**Goal: manage HA config and dashboards from Telegram.**
- /config show — read configuration.yaml (truncated to 3800 chars)
- /config check — validate config via HA API
- /integrations — list config entries grouped by domain
- /users — list HA users via WS auth/list_users
- /dash — list Lovelace views with card counts
- /dash <view> show — display view YAML (by title or path, truncated)
- /dash suggest — Claude AI generates a Lovelace view based on current entities
- Claude dashboard YAML generation prompt (no Pydantic validation — Lovelace schema is too open-ended)
- Integration tests
- **Milestone: "sugerime un dashboard para el living" generates usable Lovelace YAML**
- **Not implemented (Phase 8):** configuration.yaml edit, install/configure integrations, create users, /dash reorganize, Lovelace card add/remove

### Phase 7: Media + Energy + Snapshots (Week 13-14) ✅ DONE — v0.7.0 (2026-03-24)
**Goal: rich media interaction.**
- /camera <name> — snapshot via HA camera proxy → send photo
- Voice messages → Claude audio input → transcribe → execute as NL command
- /chart <entity> [hours] — plotly history chart → PNG → send
- /export automations|scenes|config — send as .yaml file
- /backup download — send backup file via Telegram
- /audit export [days] — send audit log as .json
- /energy today|week|month — consumption report with plotly chart
- /energy compare — current vs previous period
- Energy anomaly detection → proactive alert
- /snapshot save [name], /snapshot diff [name], /snapshot list
- Integration tests
- **Milestone: voice message "qué temperatura hay?" gets an answer**

### Phase 8: Migration + Polish + Open Source (Week 15-18) ⏳ PENDING
**Goal: production-ready, publishable.**
- /migrate check — Claude analyzes config vs HA release notes
- Detect deprecated integrations, obsolete YAML, breaking changes
- Migration assistant prompt for Claude
- Onboarding wizard on first start (Telegram guided setup)
- Quick actions (user-defined shortcuts in config.yaml)
- Entity name fuzzy matching (typo tolerance)
- Error message UX improvements
- Full test suite (aim 70%+ coverage on logic modules)
- DOCS.md — complete user documentation
- HACS repository structure preparation
- README.md with screenshots and examples
- icon.png (128x128) + logo.png (256x256)
- Security review
- Performance profiling
- **Milestone: ready to publish on GitHub + HACS**

### Fase 2 (Post-MVP, backlog)
- Automation CRUD: complex automations (choose, repeat, parallel, conditions)
- Self-healing watchdog (stale integrations, entity leaks)
- Post-mortem report generation
- Plugin system (dynamic discovery for community contributions)
- Hot-reload of modules

---

## Cost Estimation

| Service | Monthly Estimate | 2x Alert |
|---------|-----------------|----------|
| Claude API (NL, ~100 queries/day) | $5-15 | $30 |
| Claude API (YAML gen, ~10/day) | $2-5 | $10 |
| Claude API (log analysis, ~5/day) | $1-3 | $6 |
| Claude API (voice, ~5/day) | $1-2 | $4 |
| Telegram Bot API | Free | — |
| HA API (internal) | Free | — |
| **Total** | **$9-25/month** | **$50** |

---

## Security Model

| Concern | Mitigation |
|---------|-----------|
| Telegram auth | Allowlist of IDs from config.yaml, middleware enforced, all rejections logged |
| Supervisor token | Auto-injected, never stored/logged/hardcoded |
| Claude API key | In add-on options (Supervisor-encrypted), read from /data/options.json |
| AI prompt injection | System prompt restricts to valid HA services; entity_ids validated against real state |
| Destructive actions | Confirmation levels: none → single_click → double_confirm → password |
| YAML injection | Pydantic validation + HA config API check before apply |
| Auto-fix safety | Risk scoring 1-5, configurable max, auto-backup before fix |
| Audit | Every AI action logged: prompt + response + action + tokens |
| Config changes | Auto-backup before any configuration.yaml edit |
| WebSocket | Internal only, no external exposure |
| Group chat | Auth checks user_id not chat_id; only allowed users processed |

---

## ADR Log

### ADR-001: HA Add-on Architecture
**Decision:** Native HA Add-on, not standalone Docker.
**Rationale:** Auto-injected $SUPERVISOR_TOKEN, Supervisor API, native UI, watchdog restart, /data persistence, HA backup inclusion.
**Rollback:** Extract app/ → docker-compose.yml + Long-Lived Access Token.

### ADR-002: SQLite Database
**Decision:** SQLite in /data/ha_copilot.db.
**Rationale:** Zero config, included in HA backups, sufficient for single-instance I/O-bound workload. No extra add-on dependency.
**Rollback:** Migrate to PostgreSQL add-on if concurrent access becomes an issue.

### ADR-003: Python 3.12
**Decision:** Python with asyncio.
**Rationale:** HA ecosystem alignment, official Claude SDK, Pydantic integration, I/O-bound (performance irrelevant), developer velocity for nights & weekends.
**Rollback:** N/A — language change would be a rewrite.

### ADR-004: WebSocket for Real-Time Events
**Decision:** Persistent WS connection to HA Core.
**Rationale:** Instant event delivery, entity cache invalidation, proactive notifications. Auto-reconnect handles HA restarts.
**Rollback:** Disable proactive features, revert to reactive-only polling.

### ADR-005: Claude for YAML Generation
**Decision:** Claude generates automation/scene/dashboard YAML from NL.
**Rationale:** HA YAML is complex; Claude handles it well with entity context. Pydantic + HA API validation = double safety net.
**Rollback:** Remove CRUD, keep only list/toggle/trigger.

### ADR-006: Dynamic Domain Discovery
**Decision:** No hardcoded domain list.
**Rationale:** HA supports 50+ domains + custom integrations. Dynamic discovery supports any device automatically.
**Rollback:** N/A — strictly better.

### ADR-007: Risk-Scored Auto-Fix
**Decision:** 5-level risk scoring for auto-remediation.
**Rationale:** Binary on/off is too coarse. Risk levels let users precisely control what runs unattended. Auto-backup before every fix ensures safety.
**Rollback:** Set auto_fix_max_risk_score to 0 (alert only).

### ADR-008: Polling + Webhook for Telegram
**Decision:** Support both modes, configurable.
**Rationale:** Polling works everywhere (behind NAT). Webhook is more efficient but needs external URL. User chooses based on their network setup.
**Rollback:** N/A — both are always available.

### ADR-009: Conversation Memory
**Decision:** Configurable on/off with TTL and max messages.
**Rationale:** Required for contextual NL ("bajala al 30%"). But increases token usage, so must be toggleable. SQLite storage with auto-purge.
**Rollback:** Set ai_conversation_memory to false.

### ADR-010: Progressive Context Loading
**Decision:** Two-pass entity loading for Claude.
**Rationale:** Sending all entities wastes tokens (~40-60% reduction). First pass identifies needed domains, second sends only relevant entities.
**Rollback:** Send all entities (simpler, more expensive).

### ADR-011: Clean Module System (No Plugin Framework)
**Decision:** Modules implement ModuleBase ABC, registered explicitly in main.py. No auto-discovery, no plugin framework.
**Rationale:** 20 modules, single developer, nights & weekends. Plugin framework adds complexity without value until community contributions exist. Clean interface means trivial migration to plugins later.
**Rollback:** N/A — can add plugin system on top without changing modules.

### ADR-012: Idempotent Command Queue
**Decision:** FIFO async queue per user for sequential command processing.
**Rationale:** Prevents race conditions when user sends rapid messages. Ensures "prendé la sala" completes before "bajala al 50%" executes. Independent queues per user for multi-admin parallelism.
**Rollback:** Process commands concurrently (risk of race conditions).

### ADR-013: Startup Self-Test + Graceful Degradation
**Decision:** Health check all services on boot, continue in degraded mode if any fail.
**Rationale:** Never block startup due to one failed service. User gets clear report of what works and what doesn't. Degradation map ensures structured commands work even if Claude is down.
**Rollback:** N/A — strictly better than hard-failing.

### ADR-014: Self-Healing Watchdog
**Decision:** Background watchdog for stale integrations, entity leaks, with post-mortem reports.
**Rationale:** Passive monitoring catches issues users wouldn't notice (entity count slowly growing, integration silently failing). Post-mortems provide actionable insights.
**Rollback:** Disable watchdog, keep only alert engine.

### ADR-015: Scheduled Commands via HA Automations
**Decision:** NL time-based commands create one-shot HA automations instead of internal scheduler.
**Rationale:** Leverages HA's existing automation engine. Survives add-on restarts. Visible in HA UI. Tagged for easy identification and cleanup.
**Rollback:** Internal APScheduler (doesn't survive restarts).

### ADR-016: Energy Monitor
**Decision:** Built-in energy tracking with charts and anomaly detection.
**Rationale:** Energy is a major HA use case. Real-time anomaly alerts add value beyond HA's Energy dashboard. Plotly charts already in stack.
**Rollback:** Remove module, users use HA Energy dashboard directly.

### ADR-017: AI Documentation (/explain)
**Decision:** Claude explains automations, entities, and integrations in natural language.
**Rationale:** HA configs are complex YAML. NL explanation helps users understand what they have, debug issues, and onboard family members. Low token cost (one-shot, no CRUD).
**Rollback:** Remove module, users read YAML directly.

### ADR-018: Migration Assistant
**Decision:** Detect deprecated integrations, obsolete YAML, breaking changes.
**Rationale:** HA updates frequently with breaking changes. Proactive detection prevents upgrade failures. Claude can analyze config against release notes.
**Rollback:** Remove module, users check release notes manually.