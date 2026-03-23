"""
HA Copilot — async entrypoint and orchestrator.
Starts all services, runs startup self-test, then enters the bot event loop.
Gracefully tears down on SIGTERM/SIGINT.
"""
from __future__ import annotations

import asyncio
import os
import signal
import sys

from app.ai.mapper import AIActionMapper, PendingActions
from app.config import load_config
from app.core.command_queue import CommandQueueManager
from app.core.degradation import DegradationMap
from app.core.module_registry import AppContext, ModuleRegistry
from app.core.self_test import StartupSelfTest
from app.database import Database
from app.ha.client import HAClient
from app.ha.discovery import EntityDiscovery
from app.ha.supervisor import SupervisorClient
from app.ha.websocket import HAWebSocket
from app.middleware.auth import AuthMiddleware
from app.observability.health import DeadManSwitch, HealthPulse
from app.observability.logger import get_logger, setup_logging
from app.undo.manager import UndoManager

# --- Module imports ---
from app.ai.engine import AIEngineModule
from app.modules.automations import AutomationsModule
from app.modules.config_manager import ConfigManagerModule
from app.modules.dashboards import DashboardsModule
from app.modules.devices import DevicesModule
from app.modules.energy import EnergyModule
from app.modules.entities import EntitiesModule
from app.modules.explain import ExplainModule
from app.modules.log_analyzer import LogAnalyzerModule
from app.modules.migration import MigrationModule
from app.modules.quick_actions import QuickActionsModule
from app.modules.raw_api import RawApiModule
from app.modules.scenes import ScenesModule
from app.modules.scheduler import SchedulerModule
from app.modules.snapshots import SnapshotsModule
from app.modules.supervisor_mgr import SupervisorManagerModule
from app.modules.system import SystemModule
from app.modules.template_tester import TemplateTesterModule

logger = get_logger(__name__)

# Injected by Supervisor at runtime — never log or hardcode
SUPERVISOR_TOKEN = os.environ.get("SUPERVISOR_TOKEN", "")


async def main() -> None:
    # --- Config ---
    config = load_config()
    setup_logging(config.log_level)
    logger.info("ha_copilot_starting", version="0.1.0")

    # --- Infrastructure ---
    degradation = DegradationMap()
    db = Database()
    ha_client = HAClient(SUPERVISOR_TOKEN)
    supervisor_client = SupervisorClient(SUPERVISOR_TOKEN)
    websocket = HAWebSocket(SUPERVISOR_TOKEN, degradation=degradation)
    discovery = EntityDiscovery(ha_client)

    # --- Connect ---
    await db.connect()
    await db.run_migrations()
    await ha_client.connect()
    await supervisor_client.connect()
    await websocket.connect()

    # Subscribe WS state_changed events to invalidate the entity cache
    async def _on_state_changed(event: dict) -> None:
        discovery.invalidate(event.get("data", {}).get("entity_id"))

    await websocket.subscribe_events("state_changed", _on_state_changed)

    # --- Observability ---
    health_pulse = HealthPulse(config.health_pulse_interval_seconds)
    dead_man_switch = DeadManSwitch(config.dead_man_switch_timeout_seconds)
    await health_pulse.start()
    await dead_man_switch.start()

    # --- Auth ---
    auth = AuthMiddleware(config)

    # --- Module Registry (explicit registration — see ADR-011) ---
    registry = ModuleRegistry()
    registry.register(AIEngineModule())
    registry.register(DevicesModule())
    registry.register(EntitiesModule())
    registry.register(AutomationsModule())
    registry.register(ScenesModule())
    registry.register(DashboardsModule())
    registry.register(ConfigManagerModule())
    registry.register(LogAnalyzerModule())
    registry.register(SupervisorManagerModule())
    registry.register(SystemModule())
    registry.register(QuickActionsModule())
    registry.register(SchedulerModule())
    registry.register(RawApiModule())
    registry.register(TemplateTesterModule())
    registry.register(SnapshotsModule())
    registry.register(EnergyModule())
    registry.register(ExplainModule())
    registry.register(MigrationModule())

    # --- Phase 2 wiring: pending actions, undo, AI mapper ---
    pending_actions = PendingActions()
    undo_manager = UndoManager(db=db, ha_client=ha_client)
    ai_mapper = AIActionMapper(
        ha_client=ha_client,
        discovery=discovery,
        config=config,
        undo_manager=undo_manager,
        pending_actions=pending_actions,
    )

    # --- App Context ---
    app_context = AppContext(
        config=config,
        db=db,
        ha_client=ha_client,
        supervisor_client=supervisor_client,
        extra={
            "discovery": discovery,
            "mapper": ai_mapper,
            "pending_actions": pending_actions,
            "undo_manager": undo_manager,
            "degradation": degradation,
        },
    )

    await registry.setup_all(app_context)

    # --- Command Queue ---
    command_queue = CommandQueueManager(timeout=30, max_depth=10)

    # --- Bot ---
    from app.bot.handler import BotHandler

    bot = BotHandler(
        config=config,
        module_registry=registry,
        command_queue=command_queue,
        auth=auth,
        degradation=degradation,
        dead_man_switch=dead_man_switch,
    )
    await bot.setup()

    # Wire bot_send into app_context so modules can send Telegram messages
    app_context.bot_send = bot.send_message

    # Wire inline-keyboard callbacks for confirm/cancel/toggle (Phase 2)
    from app.bot import callbacks as _cb
    _cb.set_dependencies(pending_actions, ha_client)

    # --- Startup Self-Test ---
    self_test = StartupSelfTest(
        config=config,
        ha_client=ha_client,
        supervisor_client=supervisor_client,
        db=db,
        degradation=degradation,
    )
    results = await self_test.run()
    report = self_test.format_report(results)

    # Send startup report to all allowed users (plain text — no MD escaping needed)
    for uid in config.allowed_telegram_ids:
        await bot.send_message(uid, report, parse_mode="")

    # --- Start Bot ---
    if config.telegram_mode == "polling":
        await bot.start_polling()
    else:
        # Webhook mode ships in a later phase; fall back to polling
        logger.warning("webhook_not_implemented", fallback="polling")
        await bot.start_polling()

    # --- Graceful Shutdown ---
    loop = asyncio.get_running_loop()
    stop_event = asyncio.Event()

    def _on_signal() -> None:
        logger.info("shutdown_signal_received")
        stop_event.set()

    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(sig, _on_signal)
        except NotImplementedError:
            # Windows does not support add_signal_handler for all signals
            signal.signal(sig, lambda *_: _on_signal())

    logger.info("ha_copilot_running")
    await stop_event.wait()

    # --- Teardown ---
    logger.info("ha_copilot_stopping")
    await bot.stop()
    await registry.teardown_all()
    await command_queue.stop_all()
    await health_pulse.stop()
    await dead_man_switch.stop()
    await websocket.disconnect()
    await ha_client.disconnect()
    await supervisor_client.disconnect()
    await db.disconnect()
    logger.info("ha_copilot_stopped")


if __name__ == "__main__":
    asyncio.run(main())
