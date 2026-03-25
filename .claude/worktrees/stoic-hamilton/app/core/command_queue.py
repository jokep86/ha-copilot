"""
Idempotent FIFO command queue per user (see ADR-012).

Prevents race conditions when users send rapid messages.
Each user has an independent async queue — users are processed in parallel.
"""
from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass
from typing import Any, Callable, Coroutine, Optional

from app.observability.logger import get_logger

logger = get_logger(__name__)

DEFAULT_TIMEOUT_SECONDS = 30
DEFAULT_MAX_DEPTH = 10


@dataclass
class QueuedCommand:
    trace_id: str
    user_id: int
    cmd: str
    args: list[str]
    context: Any  # CommandContext — avoid circular import
    handler: Callable[..., Coroutine]


class UserCommandQueue:
    """Sequential FIFO queue for a single user."""

    def __init__(
        self,
        user_id: int,
        timeout: int = DEFAULT_TIMEOUT_SECONDS,
        max_depth: int = DEFAULT_MAX_DEPTH,
    ) -> None:
        self.user_id = user_id
        self.timeout = timeout
        self.max_depth = max_depth
        self._queue: asyncio.Queue[QueuedCommand] = asyncio.Queue()
        self._task: Optional[asyncio.Task] = None

    async def start(self) -> None:
        self._task = asyncio.create_task(self._run(), name=f"queue_{self.user_id}")

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def enqueue(self, command: QueuedCommand) -> bool:
        """Enqueue a command. Returns False if the queue is full."""
        if self._queue.qsize() >= self.max_depth:
            logger.warning(
                "command_queue_full",
                user_id=self.user_id,
                depth=self._queue.qsize(),
                max_depth=self.max_depth,
            )
            return False
        await self._queue.put(command)
        return True

    async def _run(self) -> None:
        while True:
            cmd = await self._queue.get()
            try:
                await asyncio.wait_for(
                    cmd.handler(cmd.cmd, cmd.args, cmd.context),
                    timeout=self.timeout,
                )
            except asyncio.TimeoutError:
                logger.error(
                    "command_timeout",
                    trace_id=cmd.trace_id,
                    user_id=cmd.user_id,
                    cmd=cmd.cmd,
                    timeout=self.timeout,
                )
            except Exception as exc:
                logger.error(
                    "command_error",
                    trace_id=cmd.trace_id,
                    user_id=cmd.user_id,
                    cmd=cmd.cmd,
                    error=str(exc),
                )
            finally:
                self._queue.task_done()


class CommandQueueManager:
    """Creates and manages per-user queues."""

    def __init__(
        self,
        timeout: int = DEFAULT_TIMEOUT_SECONDS,
        max_depth: int = DEFAULT_MAX_DEPTH,
    ) -> None:
        self.timeout = timeout
        self.max_depth = max_depth
        self._queues: dict[int, UserCommandQueue] = {}

    async def dispatch(
        self,
        user_id: int,
        cmd: str,
        args: list[str],
        context: Any,
        handler: Callable[..., Coroutine],
        dead_man_switch: Any = None,
    ) -> bool:
        """
        Dispatch a command to the user's queue.
        Returns False if the queue is full (caller should notify the user).
        """
        trace_id = str(uuid.uuid4())

        from structlog.contextvars import bind_contextvars
        bind_contextvars(trace_id=trace_id, user_id=user_id)

        # Attach trace_id to context so modules can propagate it
        if hasattr(context, "trace_id"):
            context.trace_id = trace_id

        queued = QueuedCommand(
            trace_id=trace_id,
            user_id=user_id,
            cmd=cmd,
            args=args,
            context=context,
            handler=handler,
        )

        q = await self._get_or_create(user_id)
        accepted = await q.enqueue(queued)

        if accepted and dead_man_switch is not None:
            dead_man_switch.reset()

        return accepted

    async def _get_or_create(self, user_id: int) -> UserCommandQueue:
        if user_id not in self._queues:
            q = UserCommandQueue(user_id, self.timeout, self.max_depth)
            await q.start()
            self._queues[user_id] = q
        return self._queues[user_id]

    async def stop_all(self) -> None:
        for q in self._queues.values():
            await q.stop()
        self._queues.clear()
