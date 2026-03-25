"""
Unit tests for CommandQueueManager and UserCommandQueue.
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core.command_queue import CommandQueueManager, UserCommandQueue


@pytest.fixture
def manager() -> CommandQueueManager:
    return CommandQueueManager(timeout=5, max_depth=3)


@pytest.mark.asyncio
async def test_dispatch_calls_handler(manager: CommandQueueManager) -> None:
    handler = AsyncMock()
    ctx = MagicMock(trace_id="")

    accepted = await manager.dispatch(
        user_id=1,
        cmd="test",
        args=["a", "b"],
        context=ctx,
        handler=handler,
    )
    assert accepted is True
    # Give the queue task a moment to process
    await asyncio.sleep(0.05)
    handler.assert_called_once_with("test", ["a", "b"], ctx)


@pytest.mark.asyncio
async def test_queue_full_returns_false(manager: CommandQueueManager) -> None:
    # Slow handler to fill the queue
    async def slow_handler(*_):
        await asyncio.sleep(10)

    ctx = MagicMock(trace_id="")

    # Fill the queue (max_depth=3, first dispatches immediately, then fills queue)
    results = []
    for _ in range(4):
        r = await manager.dispatch(
            user_id=1, cmd="x", args=[], context=ctx, handler=slow_handler
        )
        results.append(r)

    # The first 3 fit (1 being processed + 2 queued = but actually max_depth is 3 meaning queue slots)
    # At least one should be False
    assert False in results

    await manager.stop_all()


@pytest.mark.asyncio
async def test_separate_users_have_independent_queues(manager: CommandQueueManager) -> None:
    order: list[int] = []

    async def slow_handler_1(cmd, args, ctx):
        await asyncio.sleep(0.05)
        order.append(1)

    async def fast_handler_2(cmd, args, ctx):
        order.append(2)

    ctx = MagicMock(trace_id="")

    await manager.dispatch(user_id=1, cmd="a", args=[], context=ctx, handler=slow_handler_1)
    await manager.dispatch(user_id=2, cmd="b", args=[], context=ctx, handler=fast_handler_2)

    await asyncio.sleep(0.1)
    # User 2's fast handler should have completed before user 1's slow handler
    assert order.index(2) < order.index(1)

    await manager.stop_all()


@pytest.mark.asyncio
async def test_dead_man_switch_reset_on_dispatch(manager: CommandQueueManager) -> None:
    dms = MagicMock()
    dms.reset = MagicMock()
    ctx = MagicMock(trace_id="")

    await manager.dispatch(
        user_id=1,
        cmd="x",
        args=[],
        context=ctx,
        handler=AsyncMock(),
        dead_man_switch=dms,
    )
    dms.reset.assert_called_once()

    await manager.stop_all()


@pytest.mark.asyncio
async def test_trace_id_set_on_context(manager: CommandQueueManager) -> None:
    ctx = MagicMock()
    ctx.trace_id = ""

    await manager.dispatch(
        user_id=1, cmd="x", args=[], context=ctx, handler=AsyncMock()
    )
    assert ctx.trace_id != ""

    await manager.stop_all()


@pytest.mark.asyncio
async def test_handler_exception_does_not_crash_queue(manager: CommandQueueManager) -> None:
    call_count = 0

    async def failing_handler(*_):
        raise RuntimeError("test error")

    async def ok_handler(*_):
        nonlocal call_count
        call_count += 1

    ctx = MagicMock(trace_id="")

    await manager.dispatch(user_id=1, cmd="fail", args=[], context=ctx, handler=failing_handler)
    await asyncio.sleep(0.05)
    await manager.dispatch(user_id=1, cmd="ok", args=[], context=ctx, handler=ok_handler)
    await asyncio.sleep(0.05)

    assert call_count == 1

    await manager.stop_all()


@pytest.mark.asyncio
async def test_stop_all_clears_queues(manager: CommandQueueManager) -> None:
    ctx = MagicMock(trace_id="")
    await manager.dispatch(user_id=1, cmd="x", args=[], context=ctx, handler=AsyncMock())
    await manager.stop_all()
    # After stop, internal dict should be cleared
    assert manager._queues == {}
