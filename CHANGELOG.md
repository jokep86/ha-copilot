# Changelog

All notable changes to HA Copilot are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

## [Unreleased]

## [0.1.0] — 2026-03-23

### Added
- Add-on skeleton: `config.yaml`, `build.yaml`, `Dockerfile`, `run.sh`
- `AppConfig` settings loader from `/data/options.json` (Pydantic v2)
- Structured JSON logging via structlog to `/data/logs/`
- `HealthPulse` — periodic heartbeat log every N seconds (configurable)
- `DeadManSwitch` — triggers `sys.exit(1)` + Supervisor watchdog restart if silent too long
- `DegradationMap` — component health tracking with circuit breaker (3 failures → open)
- `ModuleBase` ABC — clean interface for all modules (ADR-011)
- `ModuleRegistry` — explicit module registration and lifecycle management
- `CommandQueueManager` — idempotent FIFO queue per user, prevents race conditions (ADR-012)
- `AuthMiddleware` — Telegram ID allowlist enforcement with chat_mode support
- `HAClient` — HA REST API client with exponential backoff (3 retries: 1s/2s/4s)
- `SupervisorClient` — Supervisor API client with exponential backoff
- `HAWebSocket` — WebSocket client stub (full implementation in Phase 2)
- `EntityDiscovery` — dynamic entity/domain discovery, no hardcoded lists (ADR-006)
- `Database` — SQLite via aiosqlite, WAL mode, migrations runner
- SQL migrations: `001_initial.sql` (all tables), `002_snapshots.sql`
- All Pydantic schemas: `AIAction`, `AIResponse`, `DeviceCommand`, `DeviceState`,
  `AutomationConfig`, `SceneConfig`, `DashboardConfig`, `EventSubscription`,
  `AlertCondition`, `AlertEvent`, `EnergyReport`, `EntitySnapshot`, `SnapshotDiff`,
  `SystemInfo`, `SystemMetrics`
- `StartupSelfTest` — health checks all services at boot, sends Telegram report
- `BotHandler` — Telegram bot with `/start`, `/help`, command routing, auth check
- Bot formatters (MarkdownV2), pagination (inline keyboards), callback handler
- Module stubs for all 17 planned modules (Phase 2–8)
- `AIEngineModule` stub for NL handling
- Versioned prompts in `prompts/v1/`: system, automation_creator, log_analyzer, explainer
- Golden regression test pairs in `prompts/golden/`
- Unit tests: auth (11 tests), schemas (18 tests), command_queue (7 tests),
  module_registry (8 tests), self_test (7 tests), degradation (9 tests)
- `pytest.ini` with asyncio_mode=auto
- `deploy.md`, `ADR.md`, `DOCS.md`, `translations/en.yaml`

### Architecture Decisions
- ADR-001 through ADR-018 documented in `ADR.md`
- Python 3.12, asyncio + aiohttp, python-telegram-bot 21.9, anthropic 0.52.0
- All dependencies pinned to exact versions in `requirements.txt`
