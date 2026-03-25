# Changelog

All notable changes to HA Copilot are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

## [Unreleased]

## [0.11.0] — 2026-03-25

### Added — Fase 2: Plugin System + Hot-Reload

- `app/core/plugin_loader.py` — dynamic plugin loader: scans `/data/plugins/*.py`
  using `importlib.util`; finds first concrete `ModuleBase` subclass; isolated
  failure handling (broken plugin logs and skips, doesn't block startup);
  `load_plugin_file(path)` and `load_all_plugins(registry)` public API
- `app/core/module_registry.py` — `unregister(name)` removes module + commands
  from registry without teardown; `reload_plugin(name, app, plugins_dir)` hot-reloads
  a community plugin: teardown → unregister → re-import from file → register → setup;
  raises `FileNotFoundError` (before destructive steps) if plugin file is missing so
  built-in modules cannot be accidentally unregistered
- `app/modules/plugins_module.py` — new module with commands:
  - `/plugins` — lists all loaded modules (🔌 badge for community plugins)
  - `/plugins load` — re-scans `/data/plugins/` and loads any new `.py` files
  - `/reload <name>` — hot-reloads a named community plugin without restarting
- `app/main.py` — `PluginsModule` registered; registry exposed in `AppContext.extra`;
  `load_all_plugins()` called after `setup_all` so community plugins receive
  a fully-initialized `AppContext`
- `tests/unit/test_plugin_loader.py` — 15 tests covering file loading (valid, no class,
  unnamed, syntax error, import error), `load_all_plugins` (missing dir, valid, broken
  skipped, duplicate command, multiple), `unregister`, and `reload_plugin`
  (happy path, not registered, missing file with rollback safety)

## [0.10.0] — 2026-03-25

### Added — Fase 2: Complex Automations + Automation Edit

- `prompts/v1/automation_creator.txt` — upgraded to full HA automation spec:
  `choose`, `repeat`, `parallel`, `delay`, `wait_template`, `wait_for_trigger`,
  `variables`, `stop`, `fire event`; multi-trigger; top-level conditions; `mode: queued`
  guidance for long automations
- `app/ai/yaml_generator.py` — `generate_automation_edit(current_yaml, edit_request)`:
  sends existing YAML + change description to Claude, returns updated `AutomationConfig`;
  preserves alias/id unless user asks to change them
- `app/modules/automations.py` — `/auto <query> edit <change request>` command:
  fetches existing automation JSON, calls `generate_automation_edit`, previews result
  with confirm/cancel inline keyboard, applies via `create_automation` with original id
- `tests/unit/test_yaml_generator.py` — 8 new tests: `TestGenerateAutomationEdit`
  (happy path, invalid output, Claude failure) and `TestComplexAutomationSchema`
  (choose, repeat, parallel, multiple triggers, conditions block)

## [0.9.0] — 2026-03-25

### Added — Fase 2: Self-Healing Watchdog

- `app/alerts/watchdog.py` — `SelfHealingWatchdog` with three independent asyncio
  background tasks:
  - **Stale integration check** (every 15 min): groups all HA entities by domain,
    applies per-domain staleness thresholds (`sensor` 1h, `binary_sensor` 4h,
    `climate` 30 min, `weather` 2h, default 2h); alerts if ≥2 entities in a domain
    exceed their threshold; logs to `incident_log`, sends Telegram notification
  - **Entity leak check** (every 60 min): compares current domain entity counts
    against an in-memory baseline; alerts if any domain grows >20%; baseline
    auto-resets after 24h to avoid false positives from legitimate growth;
    updates baseline after each alert to prevent repeated notifications
  - **Post-mortem generation** (every 10 min): queries `alert_log` for
    `auto_fix_attempted=1` rows not yet linked to a `post_mortem` incident;
    generates structured post-mortem entry in `incident_log`; sends Telegram
    summary with detected time, auto-fix action, result, and root cause
- `app/main.py` — `SelfHealingWatchdog` instantiated after `AlertEngine`;
  started in startup sequence, stopped gracefully in teardown
- `tests/unit/test_watchdog.py` — 17 tests covering lifecycle (start/stop),
  stale check (fresh/single/multi-stale, cross-domain, HA offline tolerance),
  entity leak (baseline set, threshold, update after alert, 24h reset, offline
  tolerance), and post-mortem generation (no rows, single row, message content)

## [0.8.0] — 2026-03-25

### Added — Phase 8: Migration + Polish

- `app/modules/migration.py` — full `MigrationModule` (`/migrate check`):
  collects HA version, installed integrations, and `configuration.yaml` snippet;
  feeds context to Claude with the migration checker prompt; displays prioritized
  [CRITICAL/WARNING/INFO] action list; tolerates partial failures (offline HA, missing config file)
- `app/modules/quick_actions.py` — full `QuickActionsModule` (`/quick`):
  reads `quick_actions` list from config.yaml; shows inline keyboard of shortcuts;
  `/quick <name>` executes directly; multi-step actions; partial-failure reporting
- `app/ha/discovery.py` — fuzzy entity matching: `find_entity()` now accepts
  `fuzzy=True` (default); when no substring match is found, falls back to
  `difflib.get_close_matches` on entity IDs and friendly names (cutoff 0.6, n=5)
- `prompts/v1/migration_checker.txt` — migration analysis prompt: structured
  [CRITICAL/WARNING/INFO] output format with issue + recommendation per item
- `app/bot/handler.py` — `/help` text rewritten to include all Phase 6–8 commands
  (config, integrations, users, dash, camera, chart, export, snapshot, energy,
  migrate, quick, audit export)
- `tests/unit/test_migration.py` — 6 tests (AI disabled, Claude called, error handling,
  HA offline tolerance)
- `tests/unit/test_quick_actions.py` — 11 tests (no config, keyboard display, execute
  by name, not found, partial failure, multi-step, fuzzy entity discovery)

## [0.7.0] — 2026-03-24

### Added — Phase 7: Media + Energy + Snapshots

- `app/ha/client.py` — `get_camera_image(entity_id)`: fetch binary camera image from
  HA camera proxy (`/api/camera_proxy/<entity_id>`) with exponential backoff
- `app/media/camera.py` — `fetch_snapshot()`: wraps HAClient camera call with
  domain-specific `CameraError`
- `app/media/charts.py` — `generate_history_chart()`: plotly line chart PNG from HA
  state history; returns `None` gracefully when plotly/kaleido not installed
- `app/media/export.py` — `export_automations()`, `export_scenes()`, `export_config()`,
  `export_audit_log()`: serialize to YAML/JSON bytes for Telegram document send
- `app/modules/media.py` — new `MediaModule` (commands: `camera`, `chart`, `export`,
  `audit`):
  - `/camera <entity>` — sends camera snapshot photo; short form `front_door` →
    `camera.front_door`
  - `/chart <entity> [hours]` — sends plotly PNG history chart; text fallback if
    plotly unavailable
  - `/export automations|scenes|config` — sends YAML file as Telegram document
  - `/audit export [days]` — sends AI audit log as JSON file
- `app/modules/snapshots.py` — full `SnapshotsModule` implementation:
  - `/snapshot save [name]` — fetches all current entity states, stores to
    `entity_snapshots` SQLite table; default name `snap_YYYYMMDD_HHMM`
  - `/snapshot diff [name]` — compares saved snapshot to current states; shows
    added/removed/changed entities with old→new state values
  - `/snapshot list` — lists saved snapshots with timestamp and entity count
- `app/modules/energy.py` — full `EnergyModule` implementation:
  - Discovers `sensor` entities with `device_class: energy` or `device_class: power`
  - `/energy today|week|month` — consumption report with delta kWh per sensor;
    sends plotly bar chart PNG when available
  - `/energy compare` — last 7 days vs previous 7 days with % change trend
  - Power sensors (W/kW) averaged; energy meters (kWh/Wh) use delta (last − first)
- `app/main.py` — registered `MediaModule`
- `tests/unit/test_snapshots.py` — 12 tests (save, list, diff, edge cases,
  `_compute_diff` helper)
- `tests/unit/test_energy.py` — 13 tests (period range, delta computation, format,
  module commands)
- `tests/unit/test_media.py` — 12 tests (camera, chart, export, audit)

## [0.6.0] — 2026-03-24

### Added — Phase 6: Config + Dashboard Management

- `app/ha/websocket.py` — `send_command()`: send arbitrary WS command and await result
  (used for Lovelace config fetch and auth/list_users)
- `app/ha/client.py` — `get_config_entries()`: fetch config entries from
  `/api/config/config_entries/entry` (integrations list)
- `app/main.py` — added `websocket` to `AppContext.extra` for module access
- `app/modules/config_manager.py` — full `ConfigManagerModule` implementation:
  - `/config [show]` — read `/homeassistant/configuration.yaml` from disk, truncated
    to 3800 chars; displayed as YAML code block
  - `/config check` — call HA config check API, reports valid/invalid + errors
  - `/integrations` — list config entries grouped by domain with entry count
  - `/users` — list HA users via WS `auth/list_users` with admin/active flags
- `app/modules/dashboards.py` — full `DashboardsModule` implementation:
  - `/dash` — list Lovelace views from default dashboard (via WS `lovelace/config`)
    with card counts per view
  - `/dash <view> show` — display full view YAML (by title or path, truncated)
  - `/dash suggest` — Claude AI generates a Lovelace view based on current entities
- `app/ai/yaml_generator.py` — `generate_dashboard()`: Claude-powered Lovelace view
  YAML generation (returns raw YAML string for user review; no Pydantic validation —
  Lovelace schema is too open-ended)
- `prompts/v1/dashboard_creator.txt` — dashboard YAML generation prompt with card type
  selection rules and grouping guidance
- `tests/unit/test_config_manager.py` — 9 unit tests (config show, check, integrations,
  users, error handling)
- `tests/unit/test_dashboards.py` — 9 unit tests (list views, show by title/path,
  not found, WS error, suggest with generator mock)

## [0.5.0] — 2026-03-23

### Added — Phase 5: Proactive Alerts + Notifications

- `app/events/filters.py` — `EventFilter`: domain filter, entity pattern (regex),
  per-entity cooldown (in-memory monotonic clock), `reset_cooldown()`
- `app/events/notifier.py` — `Notifier`: sends Telegram message to all allowed users,
  logs every send to `notification_log`; `set_bot_send()` injected after bot setup
- `app/events/listener.py` — `EventListener`: subscribes to all configured
  `notification_events` via HAWebSocket; applies `EventFilter`; formats state_changed
  and automation_triggered events; per-user enable/disable
- `app/alerts/conditions.py` — `AlertConditionChecker`: evaluates `device_unavailable`
  (entities with state="unavailable"), `low_battery` (battery sensor < threshold),
  `disk_usage` (Supervisor host disk > threshold_percent)
- `app/alerts/auto_fix.py` — `AutoFix`: risk-scored remediation (risk 1-5); integration
  reload for unavailable zwave_js/zigbee2mqtt/mqtt/modbus devices (risk 2); auto-backup
  before risk ≥ 3 actions; respects `auto_fix_max_risk_score` config
- `app/alerts/engine.py` — `AlertEngine`: asyncio background loop at
  `health_check_interval_seconds`; DB-backed cooldown check per alert_type+entity_id;
  logs to `alert_log`; triggers `AutoFix` and sends notification; `get_recent(n)`
- `app/alerts/digest.py` — `DailyDigest`: sends health summary at configured time
  (component status + 24h alert counts + auto-fix count)
- `app/modules/notifications.py` — `NotificationsModule`: `/notify on|off` (per-user
  toggle), `/subs` (list active subscription types)
- `app/modules/alerts_module.py` — `AlertsModule`: `/alerts [N]` shows last N alerts
  from `alert_log` with severity icons and auto-fix details
- `main.py` wired: `Notifier` → `EventListener.start(ws)` → `AlertEngine.start()` →
  `DailyDigest.start()`; all injected into `AppContext.extra`
- Unit tests: event_filters (10 tests), auto_fix (6 tests)

## [0.4.0] — 2026-03-23

### Added — Phase 4: Automation/Scene CRUD + Scheduling

- `app/ai/yaml_generator.py` — `YAMLGenerator`: loads versioned prompts, builds entity
  context, calls Claude, strips markdown fences, parses YAML with ruamel.yaml,
  validates with Pydantic (`AutomationConfig` / `SceneConfig`)
- `prompts/v1/scene_creator.txt` — scene YAML generation prompt with entity context
- `AutomationsModule` — full implementation:
  - `/auto` — paginated list with `ha_copilot` tag indicator
  - `/auto <query> on|off|trigger|show` — enable/disable/trigger/show YAML
  - `/auto <query> delete` — delete with inline confirm/cancel keyboard via `PendingActions`
  - `/auto create <description>` — Claude YAML → Pydantic validation → preview →
    inline confirm → `HAClient.create_automation()`
- `ScenesModule` — full implementation:
  - `/scenes` — list all scenes
  - `/scene <query> activate|delete` — activate or delete with inline confirm
  - `/scene create <description>` — Claude YAML → preview → inline confirm → create
- `SchedulerModule` — full implementation:
  - `/schedule list` — lists automations tagged `ha_copilot_scheduled`
  - `/schedule cancel <id_or_alias>` — deletes the scheduled automation
  - NL scheduling path (`/schedule create`) reserved for AIActionMapper extension
- `ExplainModule` — full implementation:
  - `/explain auto <query>` — Claude explains automation triggers/conditions/actions
  - `/explain entity <entity_id>` — Claude explains entity source and usage
  - `/explain integration <name>` — Claude explains integration with related entities
  - Uses `prompts/v1/explainer.txt`; AI disabled guard
- Unit tests: automations (10 tests), explain (6 tests)

## [0.3.0] — 2026-03-23

### Added — Phase 3: System Admin + Power Tools

- `SystemModule` — `/sys`: component health dashboard (DegradationMap emojis, HA version,
  entity count by domain, Supervisor version, host info, HA OS version)
- `SupervisorManagerModule` — full implementation:
  - `/addons` — lists all add-ons with state, version, update-available flag
  - `/addon <slug> info` — detailed add-on information
  - `/addon <slug> restart [confirm]` — restart with double-confirm guard
  - `/backup list` — lists backups with date, size, type
  - `/backup create` — creates full backup
  - `/restart core|supervisor [confirm]` — restart with double-confirm
  - `/reboot [confirm]` — host reboot with double-confirm
- `LogAnalyzerModule` — full implementation:
  - `/logs [source] [level]` — reads plain-text logs from core/supervisor/host/<slug>,
    optional level filter (ERROR, WARNING, etc.), truncated to last 200 lines
  - `/logs analyze [source]` — extracts error/warning lines → Claude diagnosis
    using `prompts/v1/log_analyzer.txt` prompt
- `RawApiModule` — full implementation:
  - `/raw GET|POST|PUT|DELETE <path> [body]` — direct HA REST API call
  - `/raw SUP GET|POST <path>` — direct Supervisor API call
  - GET executes immediately; POST/PUT/DELETE require `confirm` keyword
  - Results formatted as JSON code block; all calls logged to `raw_api_log`
- `TemplateTesterModule` — full implementation:
  - `/template <jinja2>` — evaluate once via HA `POST /api/template`
  - `/template watch <jinja2>` — re-evaluate every 5s for 60s, edit message in-place
- `SupervisorClient.get_logs()` — fixed: logs are plain text; added `_request_text()`
  method alongside existing `_request()` (which expects JSON)
- `degradation` injected into `AppContext.extra` for SystemModule access
- Unit tests: system (6 tests), supervisor_mgr (11 tests), log_analyzer (7 tests)

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
