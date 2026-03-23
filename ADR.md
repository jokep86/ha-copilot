# Architecture Decision Records

Log of all significant design decisions for ha-copilot.
Format: Decision → Rationale → Alternatives → Rollback.

---

## ADR-001: HA Add-on Architecture
**Date:** 2026-03-23
**Decision:** Native HA Add-on, not standalone Docker.
**Rationale:** Auto-injected `$SUPERVISOR_TOKEN`, Supervisor API access, native HA UI, watchdog restart, `/data` persistence, included in HA backups.
**Alternatives:** Standalone Docker with Long-Lived Access Token.
**Rollback:** Extract `app/` → `docker-compose.yml` + Long-Lived Access Token.

---

## ADR-002: SQLite Database
**Date:** 2026-03-23
**Decision:** SQLite in `/data/ha_copilot.db` via aiosqlite.
**Rationale:** Zero config, included in HA backups, sufficient for single-instance I/O-bound workload. No external dependency.
**Alternatives:** PostgreSQL add-on, Redis.
**Rollback:** Migrate to PostgreSQL add-on if concurrent access becomes an issue.

---

## ADR-003: Python 3.12 + asyncio
**Date:** 2026-03-23
**Decision:** Python with asyncio + aiohttp.
**Rationale:** HA ecosystem alignment, official Claude SDK, Pydantic integration, I/O-bound project (performance irrelevant), developer velocity.
**Alternatives:** Node.js, Go.
**Rollback:** N/A — language change would be a rewrite.

---

## ADR-004: WebSocket for Real-Time Events
**Date:** 2026-03-23
**Decision:** Persistent WS connection to HA Core.
**Rationale:** Instant event delivery, entity cache invalidation, proactive notifications. Auto-reconnect handles HA restarts.
**Alternatives:** REST polling every N seconds.
**Rollback:** Disable proactive features, revert to reactive-only polling.

---

## ADR-005: Claude for YAML Generation
**Date:** 2026-03-23
**Decision:** Claude generates automation/scene/dashboard YAML from natural language.
**Rationale:** HA YAML is complex; Claude handles it well with entity context. Pydantic + HA API validation = double safety net.
**Alternatives:** Rule-based templates, predefined patterns.
**Rollback:** Remove CRUD, keep only list/toggle/trigger.

---

## ADR-006: Dynamic Domain Discovery
**Date:** 2026-03-23
**Decision:** No hardcoded domain list. Discovery at runtime from HA state.
**Rationale:** HA supports 50+ domains + custom integrations. Dynamic discovery supports any device automatically.
**Alternatives:** Hardcoded list of common domains.
**Rollback:** N/A — strictly better.

---

## ADR-007: Risk-Scored Auto-Fix
**Date:** 2026-03-23
**Decision:** 5-level risk scoring (1=trivial → 5=critical) for auto-remediation.
**Rationale:** Binary on/off too coarse. Risk levels let users precisely control what runs unattended. Auto-backup before every fix ensures safety.
**Alternatives:** Binary enabled/disabled, manual-only.
**Rollback:** Set `auto_fix_max_risk_score: 0` (alert only, no auto-fix).

---

## ADR-008: Polling + Webhook for Telegram
**Date:** 2026-03-23
**Decision:** Support both modes, configurable via `telegram_mode`.
**Rationale:** Polling works everywhere (behind NAT). Webhook is more efficient but needs external URL. User chooses.
**Alternatives:** Polling-only, webhook-only.
**Rollback:** N/A — both are always available.

---

## ADR-009: Conversation Memory
**Date:** 2026-03-23
**Decision:** Configurable on/off with TTL and max messages.
**Rationale:** Required for contextual NL ("lower it to 30%"). Toggleable to control token usage. SQLite storage with auto-purge.
**Alternatives:** Always-on, always-off.
**Rollback:** Set `ai_conversation_memory: false`.

---

## ADR-010: Progressive Context Loading
**Date:** 2026-03-23
**Decision:** Two-pass entity loading for Claude (domain list → relevant entities).
**Rationale:** Sending all entities wastes ~40-60% tokens. First pass identifies needed domains, second sends only relevant entities.
**Alternatives:** Send all entities always, send no entities (entity_id only).
**Rollback:** Send all entities in every request (simpler, more expensive).

---

## ADR-011: Clean Module System (No Plugin Framework)
**Date:** 2026-03-23
**Decision:** Modules implement `ModuleBase` ABC, registered explicitly in `main.py`. No auto-discovery.
**Rationale:** 20 modules, single developer, nights & weekends. Plugin framework adds complexity without value until community contributions exist. Clean interface means trivial future migration.
**Alternatives:** Auto-discovery via entry points, dynamic import.
**Rollback:** N/A — can add plugin system on top without changing modules.

---

## ADR-012: Idempotent Command Queue
**Date:** 2026-03-23
**Decision:** FIFO async queue per user, independent queues across users.
**Rationale:** Prevents race conditions ("turn on lights" + "dim to 50%" processed in order). Users process in parallel.
**Alternatives:** Concurrent processing per user.
**Rollback:** Process commands concurrently (risk of race conditions).

---

## ADR-013: Startup Self-Test + Graceful Degradation
**Date:** 2026-03-23
**Decision:** Health check all services on boot; continue in degraded mode if any fail.
**Rationale:** Never block startup due to one failed service. User gets clear report. Degradation map ensures structured commands work even if Claude is down.
**Alternatives:** Fail fast on any service failure.
**Rollback:** N/A — strictly better than hard-failing.

---

## ADR-014: Self-Healing Watchdog (Fase 2)
**Date:** 2026-03-23
**Decision:** Background watchdog for stale integrations, entity leaks, post-mortem reports.
**Rationale:** Passive monitoring catches issues users wouldn't notice.
**Alternatives:** Manual monitoring only.
**Rollback:** Disable watchdog, keep only alert engine.

---

## ADR-015: Scheduled Commands via HA Automations
**Date:** 2026-03-23
**Decision:** NL time-based commands create one-shot HA automations.
**Rationale:** Leverages HA's automation engine. Survives add-on restarts. Visible in HA UI. Tagged for easy identification.
**Alternatives:** Internal APScheduler.
**Rollback:** Internal APScheduler (doesn't survive restarts).

---

## ADR-016: Energy Monitor
**Date:** 2026-03-23
**Decision:** Built-in energy tracking with charts and anomaly detection.
**Rationale:** Energy is a major HA use case. Real-time anomaly alerts add value beyond HA's Energy dashboard.
**Alternatives:** Point users to HA Energy dashboard.
**Rollback:** Remove module.

---

## ADR-017: AI Documentation (/explain)
**Date:** 2026-03-23
**Decision:** Claude explains automations, entities, and integrations in natural language.
**Rationale:** HA configs are complex YAML. NL explanation helps users understand their setup.
**Alternatives:** Raw YAML display only.
**Rollback:** Remove module.

---

## ADR-018: Migration Assistant
**Date:** 2026-03-23
**Decision:** Detect deprecated integrations, obsolete YAML, breaking changes.
**Rationale:** HA updates frequently with breaking changes. Proactive detection prevents upgrade failures.
**Alternatives:** Users check release notes manually.
**Rollback:** Remove module.
