"""
Unit tests for SchedulerModule.
Covers: list (empty, with results), cancel (no query, not found, success),
and handle_command routing.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.modules.scheduler import SchedulerModule

_TAG = "ha_copilot_scheduled"

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_SCHEDULED = [
    {
        "id": "sch_001",
        "alias": "Turn off lights in 30 min",
        "description": f"Created by ha-copilot. {_TAG}",
        "trigger": [{"platform": "time", "at": "22:30:00"}],
        "action": [{"service": "light.turn_off"}],
    },
    {
        "id": "sch_002",
        "alias": "Lock door in 10 min",
        "description": f"Scheduled. {_TAG}",
        "trigger": [{"platform": "time", "at": "22:10:00"}],
        "action": [{"service": "lock.lock"}],
    },
]

_UNSCHEDULED = [
    {
        "id": "reg_001",
        "alias": "Turn on lights at sunrise",
        "description": "",
        "trigger": [{"platform": "sun", "event": "sunrise"}],
        "action": [{"service": "light.turn_on"}],
    },
]


def _make_app(autos=None):
    ha = MagicMock()
    ha.get_automations = AsyncMock(return_value=autos if autos is not None else [])
    ha.delete_automation = AsyncMock()

    app = MagicMock()
    app.ha_client = ha
    return app, ha


def _ctx():
    ctx = MagicMock()
    ctx.user_id = 1
    ctx.update = MagicMock()
    ctx.update.message = MagicMock()
    ctx.update.message.reply_text = AsyncMock()
    return ctx


# ---------------------------------------------------------------------------
# _cmd_list
# ---------------------------------------------------------------------------

class TestCmdList:
    async def test_no_scheduled_automations(self):
        mod = SchedulerModule()
        app, ha = _make_app(autos=_UNSCHEDULED)
        await mod.setup(app)
        ctx = _ctx()

        await mod.handle_command("schedule", ["list"], ctx)

        ctx.update.message.reply_text.assert_awaited_once()
        reply = ctx.update.message.reply_text.call_args[0][0]
        assert "No pending" in reply

    async def test_shows_scheduled_automations(self):
        mod = SchedulerModule()
        app, ha = _make_app(autos=_SCHEDULED + _UNSCHEDULED)
        await mod.setup(app)
        ctx = _ctx()

        await mod.handle_command("schedule", ["list"], ctx)

        ctx.update.message.reply_text.assert_awaited_once()
        reply = ctx.update.message.reply_text.call_args[0][0]
        # Both scheduled aliases should appear
        assert "Turn off lights" in reply
        assert "Lock door" in reply
        # Regular automation should NOT appear
        assert "sunrise" not in reply

    async def test_shows_trigger_time_when_present(self):
        mod = SchedulerModule()
        app, ha = _make_app(autos=_SCHEDULED)
        await mod.setup(app)
        ctx = _ctx()

        await mod.handle_command("schedule", ["list"], ctx)

        reply = ctx.update.message.reply_text.call_args[0][0]
        assert "22:30:00" in reply

    async def test_ha_error_shows_error_message(self):
        mod = SchedulerModule()
        app, ha = _make_app()
        ha.get_automations = AsyncMock(side_effect=Exception("HA unreachable"))
        await mod.setup(app)
        ctx = _ctx()

        await mod.handle_command("schedule", ["list"], ctx)

        reply = ctx.update.message.reply_text.call_args[0][0]
        assert "Cannot get automations" in reply or "HA unreachable" in reply


# ---------------------------------------------------------------------------
# _cmd_cancel
# ---------------------------------------------------------------------------

class TestCmdCancel:
    async def test_no_query_shows_usage(self):
        mod = SchedulerModule()
        app, ha = _make_app(autos=_SCHEDULED)
        await mod.setup(app)
        ctx = _ctx()

        await mod.handle_command("schedule", ["cancel"], ctx)

        reply = ctx.update.message.reply_text.call_args[0][0]
        assert "Usage" in reply

    async def test_not_found_shows_message(self):
        mod = SchedulerModule()
        app, ha = _make_app(autos=_SCHEDULED)
        await mod.setup(app)
        ctx = _ctx()

        await mod.handle_command("schedule", ["cancel", "nonexistent_automation"], ctx)

        reply = ctx.update.message.reply_text.call_args[0][0]
        assert "nonexistent_automation" in reply or "No scheduled" in reply

    async def test_cancel_by_exact_id(self):
        mod = SchedulerModule()
        app, ha = _make_app(autos=_SCHEDULED)
        await mod.setup(app)
        ctx = _ctx()

        await mod.handle_command("schedule", ["cancel", "sch_001"], ctx)

        ha.delete_automation.assert_awaited_once_with("sch_001")
        reply = ctx.update.message.reply_text.call_args[0][0]
        assert "cancelled" in reply.lower() or "Turn off lights" in reply

    async def test_cancel_by_partial_alias(self):
        mod = SchedulerModule()
        app, ha = _make_app(autos=_SCHEDULED)
        await mod.setup(app)
        ctx = _ctx()

        await mod.handle_command("schedule", ["cancel", "lock", "door"], ctx)

        ha.delete_automation.assert_awaited_once_with("sch_002")

    async def test_cancel_ha_error_shows_message(self):
        mod = SchedulerModule()
        app, ha = _make_app(autos=_SCHEDULED)
        ha.delete_automation = AsyncMock(side_effect=Exception("permission denied"))
        await mod.setup(app)
        ctx = _ctx()

        await mod.handle_command("schedule", ["cancel", "sch_001"], ctx)

        reply = ctx.update.message.reply_text.call_args[0][0]
        assert "Cancel failed" in reply or "permission denied" in reply

    async def test_cancel_ha_error_fetching_automations(self):
        mod = SchedulerModule()
        app, ha = _make_app()
        ha.get_automations = AsyncMock(side_effect=Exception("connection error"))
        await mod.setup(app)
        ctx = _ctx()

        await mod.handle_command("schedule", ["cancel", "sch_001"], ctx)

        reply = ctx.update.message.reply_text.call_args[0][0]
        assert "Cannot get automations" in reply or "connection error" in reply


# ---------------------------------------------------------------------------
# handle_command routing
# ---------------------------------------------------------------------------

class TestHandleCommandRouting:
    async def test_default_subcommand_is_list(self):
        mod = SchedulerModule()
        app, ha = _make_app(autos=[])
        await mod.setup(app)
        ctx = _ctx()

        # No args → defaults to list
        await mod.handle_command("schedule", [], ctx)

        ctx.update.message.reply_text.assert_awaited_once()
        reply = ctx.update.message.reply_text.call_args[0][0]
        assert "No pending" in reply

    async def test_unknown_subcommand_shows_usage(self):
        mod = SchedulerModule()
        app, ha = _make_app()
        await mod.setup(app)
        ctx = _ctx()

        await mod.handle_command("schedule", ["foobar"], ctx)

        reply = ctx.update.message.reply_text.call_args[0][0]
        assert "Usage" in reply
