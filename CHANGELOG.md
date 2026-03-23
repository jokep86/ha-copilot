# Changelog

All notable changes to HA Copilot are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

## [Unreleased]

## [0.2.0] — 2026-03-23

### Added — Phase 2: Device Control + AI Engine

- `HAWebSocket` — full implementation: persistent connection, HA auth handshake,
  event subscriptions, auto-reconnect (5/10/30/60s delays), background retry every 60s,
  circuit breaker via `DegradationMap`
- `EntityDiscovery` — in-memory entity cache with 5-min TTL fallback; WebSocket
  `state_changed` events invalidate only the changed entity (~90% reduction in HA API calls)
- `AIEngineModule` — full NL interpreter: progressive context loading (ADR-010),
  conversation memory, fallback chain (retry 2s/4s → cache → alert), daily token budget,
  AI Decision Audit Log, language auto-detection
- `ContextLoader` — two-pass entity context: keyword heuristic selects relevant domains,
  sends only those to Claude (EN + ES keyword coverage)
- `ConversationMemory` — SQLite-backed message history, configurable TTL + max messages
- `AIAuditLog` — logs every Claude call with tokens, latency, raw prompt/response;
  daily budget tracking with UPSERT to `token_usage`
- `AIActionMapper` — routes `AIResponse` actions to HA API; applies confirmation levels;
  saves undo state before every mutation
- `PendingActions` — in-memory store (60s TTL) for actions awaiting inline-keyboard confirmation
- `UndoManager` — saves pre-mutation entity state to `undo_log`; `/undo` reapplies
  previous state (on/off toggle or brightness/temperature for numeric states)
- `DevicesModule` — `/devices [domain]`: domain summary with inline buttons, or paginated
  entity list with toggle buttons (2 per row); `/status <entity>`; `/toggle <entity>`
- `EntitiesModule` — `/entities [domain]`: paginated list with friendly name, entity ID,
  state + unit; `/history <entity> [hours]`: last 15 state changes (1–168h range)
- Inline keyboard callbacks: `confirm:ID` / `cancel:ID` (pending action flow),
  `domain:X` (domain hint), `toggle:ENTITY_ID` (direct HA call via callback)
- `main.py` wired with all Phase 2 components: WS state_changed → discovery.invalidate,
  `PendingActions` + `UndoManager` + `AIActionMapper` in `AppContext.extra`,
  `callbacks.set_dependencies()` for inline keyboards
- Versioned system prompt with progressive context placeholders
  (`{entity_context}`, `{conversation_history}`, `{entity_aliases}`)
- Unit tests: ai_mapper (15 tests), conversation (5 tests), devices (10 tests)

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
