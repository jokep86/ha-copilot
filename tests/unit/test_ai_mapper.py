"""
Unit tests for AIActionMapper and PendingActions.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from app.ai.mapper import AIActionMapper, PendingActions
from app.schemas.ai_action import ActionType, AIAction, AIResponse


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_context(user_id: int = 1) -> MagicMock:
    ctx = MagicMock()
    ctx.user_id = user_id
    ctx.chat_id = user_id
    ctx.update = MagicMock()
    ctx.update.message = MagicMock()
    ctx.update.message.reply_text = AsyncMock()
    return ctx


def _make_action(**kwargs) -> AIAction:
    defaults = {
        "action_type": ActionType.CALL_SERVICE,
        "domain": "light",
        "service": "turn_on",
        "entity_id": "light.sala",
        "entity_ids": [],
        "service_data": {},
        "confidence": 0.9,
    }
    defaults.update(kwargs)
    return AIAction(**defaults)


def _make_mapper(config=None) -> tuple[AIActionMapper, MagicMock, MagicMock, MagicMock, PendingActions]:
    ha = MagicMock()
    ha.get_state = AsyncMock(return_value={"state": "off", "attributes": {"friendly_name": "Sala"}})
    ha.call_service = AsyncMock()

    discovery = MagicMock()
    discovery.get_entities_by_domain = AsyncMock(return_value=[])
    discovery.get_all_states = AsyncMock(return_value=[])

    if config is None:
        config = MagicMock()
        config.confirmation_levels = MagicMock()
        config.confirmation_levels.none = ["get_state", "list_entities", "system_info"]

    undo = MagicMock()
    undo.save = AsyncMock()

    pending = PendingActions()

    mapper = AIActionMapper(
        ha_client=ha,
        discovery=discovery,
        config=config,
        undo_manager=undo,
        pending_actions=pending,
    )
    return mapper, ha, discovery, undo, pending


# ---------------------------------------------------------------------------
# PendingActions
# ---------------------------------------------------------------------------

class TestPendingActions:
    async def test_store_and_confirm(self):
        pending = PendingActions()
        executor = AsyncMock(return_value=None)
        ctx = _make_context()
        action = _make_action()

        action_id = await pending.store(
            action=action, trace_id="t1", user_id=1,
            executor=executor, context=ctx,
        )
        assert len(action_id) == 8

        ok = await pending.confirm(action_id)
        assert ok is True
        executor.assert_awaited_once_with(action, ctx)

    async def test_confirm_missing_id_returns_false(self):
        pending = PendingActions()
        ok = await pending.confirm("nonexistent")
        assert ok is False

    async def test_cancel_removes_entry(self):
        pending = PendingActions()
        executor = AsyncMock()
        ctx = _make_context()
        action_id = await pending.store(
            action=_make_action(), trace_id="t1", user_id=1,
            executor=executor, context=ctx,
        )
        ok = await pending.cancel(action_id)
        assert ok is True
        # Confirm after cancel must return False
        assert await pending.confirm(action_id) is False
        executor.assert_not_awaited()

    async def test_confirm_expired_returns_false(self):
        pending = PendingActions()
        pending.TTL_SECONDS = 0  # Force immediate expiry
        executor = AsyncMock()
        ctx = _make_context()
        action_id = await pending.store(
            action=_make_action(), trace_id="t1", user_id=1,
            executor=executor, context=ctx,
        )
        ok = await pending.confirm(action_id)
        assert ok is False
        executor.assert_not_awaited()

    async def test_executor_exception_returns_false(self):
        pending = PendingActions()
        executor = AsyncMock(side_effect=RuntimeError("boom"))
        ctx = _make_context()
        action_id = await pending.store(
            action=_make_action(), trace_id="t1", user_id=1,
            executor=executor, context=ctx,
        )
        ok = await pending.confirm(action_id)
        assert ok is False


# ---------------------------------------------------------------------------
# AIActionMapper — read-only actions execute immediately
# ---------------------------------------------------------------------------

class TestAIActionMapperReadOnly:
    async def test_get_state_executes_immediately(self):
        mapper, ha, *_ = _make_mapper()
        ctx = _make_context()
        action = _make_action(action_type=ActionType.GET_STATE, entity_id="sensor.temp")
        response = AIResponse(actions=[action], trace_id="t1")

        await mapper.execute(response, ctx)

        ha.get_state.assert_awaited_once_with("sensor.temp")
        ctx.update.message.reply_text.assert_awaited_once()

    async def test_list_entities_executes_immediately(self):
        mapper, ha, discovery, *_ = _make_mapper()
        ctx = _make_context()
        discovery.get_entities_by_domain = AsyncMock(return_value=[
            {"entity_id": "light.sala", "state": "on", "attributes": {"friendly_name": "Sala"}}
        ])
        action = _make_action(action_type=ActionType.LIST_ENTITIES, domain="light")
        response = AIResponse(actions=[action], trace_id="t1")

        await mapper.execute(response, ctx)

        ctx.update.message.reply_text.assert_awaited_once()

    async def test_empty_response_sends_clarification(self):
        mapper, *_ = _make_mapper()
        ctx = _make_context()
        response = AIResponse(actions=[], trace_id="t1")

        await mapper.execute(response, ctx)

        ctx.update.message.reply_text.assert_awaited_once()
        text = ctx.update.message.reply_text.call_args[0][0]
        assert "understand" in text.lower() or "rephras" in text.lower()

    async def test_unknown_action_replies(self):
        mapper, *_ = _make_mapper()
        ctx = _make_context()
        action = _make_action(action_type=ActionType.UNKNOWN)
        response = AIResponse(actions=[action], trace_id="t1")

        await mapper.execute(response, ctx)

        ctx.update.message.reply_text.assert_awaited_once()


# ---------------------------------------------------------------------------
# AIActionMapper — confirmation flow
# ---------------------------------------------------------------------------

class TestAIActionMapperConfirmation:
    async def test_call_service_sends_confirm_keyboard(self):
        mapper, ha, *_, pending = _make_mapper()
        ctx = _make_context()
        action = _make_action(action_type=ActionType.CALL_SERVICE)
        response = AIResponse(actions=[action], trace_id="t1")

        await mapper.execute(response, ctx)

        # Should NOT have called the service yet
        ha.call_service.assert_not_awaited()
        # Should have sent the confirm keyboard
        ctx.update.message.reply_text.assert_awaited_once()
        # Should have stored pending action
        assert len(pending._actions) == 1

    async def test_call_service_in_none_list_executes_immediately(self):
        config = MagicMock()
        config.confirmation_levels = MagicMock()
        config.confirmation_levels.none = ["call_service"]

        mapper, ha, *_ = _make_mapper(config=config)
        ctx = _make_context()
        ha.get_state = AsyncMock(return_value={"state": "off", "attributes": {}})

        action = _make_action(action_type=ActionType.CALL_SERVICE)
        response = AIResponse(actions=[action], trace_id="t1")

        await mapper.execute(response, ctx)

        ha.call_service.assert_awaited_once()

    async def test_do_call_service_saves_undo(self):
        mapper, ha, _, undo, _ = _make_mapper()
        ctx = _make_context()
        ha.get_state = AsyncMock(return_value={"state": "on", "attributes": {}})

        action = _make_action(
            action_type=ActionType.CALL_SERVICE,
            entity_id="light.sala",
            entity_ids=[],
        )
        await mapper._do_call_service(action, ctx)

        undo.save.assert_awaited_once()
        ha.call_service.assert_awaited_once()
