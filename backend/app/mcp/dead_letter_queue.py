"""Dead Letter Queue (DLQ) — handles failed MCP tool calls.

When an MCP tool call fails due to rate limiting or downtime, the task
is persisted as an ``AsyncTask`` row in the database. The background
DLQ worker periodically retries failed tasks, incrementing retry_count
each attempt. Tasks that exceed ``max_retries`` are moved to ``dead_letter``
status for manual intervention via the SecOps Dashboard.

Flow:
    Tool call fails → AsyncTask (status=failed) → DLQ worker retries
        ├─ success → status=completed + task_update event
        └─ exhausted → status=dead_letter + task_update event
"""

import asyncio
import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Optional, Callable, Awaitable

from loguru import logger

from app.core.events import event_bus
from app.db.database import async_session
from app.db.repositories import TaskRepository


# ============================================================================
# Data model (mirrors AsyncTask DB model for in-memory convenience)
# ============================================================================


class DLQTaskStatus(str, Enum):
    PENDING = "pending"
    RETRYING = "retrying"
    DEAD_LETTER = "dead_letter"
    COMPLETED = "completed"


@dataclass
class DLQTask:
    """A task that has entered the dead letter queue."""
    id: str
    tool_name: str
    payload: dict = field(default_factory=dict)
    status: DLQTaskStatus = DLQTaskStatus.PENDING
    retry_count: int = 0
    max_retries: int = 3
    last_error: Optional[str] = None
    created_at: datetime = field(default_factory=datetime.utcnow)
    last_retry_at: Optional[datetime] = None


class DeadLetterQueue:
    """In-memory dead letter queue for MCP tool failures.

    This is the in-memory overlay — the database ``async_tasks`` table
    is the persistent source of truth.  The DLQ worker queries the DB
    directly; this in-memory queue exists for fast lookups and testing.
    """

    def __init__(self) -> None:
        self._queue: dict[str, DLQTask] = {}

    def enqueue(self, task: DLQTask) -> None:
        self._queue[task.id] = task

    def dequeue(self, task_id: str) -> Optional[DLQTask]:
        return self._queue.pop(task_id, None)

    def get_pending(self) -> list[DLQTask]:
        return [t for t in self._queue.values() if t.status == DLQTaskStatus.PENDING]

    def mark_dead(self, task_id: str, error: str) -> None:
        if task_id in self._queue:
            self._queue[task_id].status = DLQTaskStatus.DEAD_LETTER
            self._queue[task_id].last_error = error

    def mark_completed(self, task_id: str) -> None:
        if task_id in self._queue:
            self._queue[task_id].status = DLQTaskStatus.COMPLETED

    @property
    def dead_count(self) -> int:
        return sum(1 for t in self._queue.values() if t.status == DLQTaskStatus.DEAD_LETTER)

    @property
    def pending_count(self) -> int:
        return sum(1 for t in self._queue.values() if t.status == DLQTaskStatus.PENDING)


# Global singleton
dead_letter_queue = DeadLetterQueue()


# ============================================================================
# Tool-name → retry-function registry
# ============================================================================

_retry_registry: dict[str, Callable[..., Awaitable[tuple[bool, str]]]] = {}


def register_retry_handler(tool_name: str, handler: Callable[..., Awaitable[tuple[bool, str]]]) -> None:
    """Register a retry function for a named MCP tool.

    The handler receives the task's ``payload`` as keyword arguments,
    re-executes the tool, and returns ``(success: bool, message: str)``.
    """
    _retry_registry[tool_name] = handler


# ============================================================================
# DLQ retry logic (used by the background worker)
# ============================================================================


async def retry_failed_tasks() -> int:
    """Poll DB for failed tasks with retry budget and attempt each one.

    Called periodically by the DLQ background worker.  For each task:
    1. Look up the retry handler from the registry.
    2. Re-execute the tool.
    3. Update the DB row and publish a ``task_update`` event.

    Returns:
        Number of tasks that were retried this cycle.
    """
    try:
        async with async_session() as db:
            tasks = await TaskRepository.list_all(db, status="failed", limit=20)
    except Exception as exc:
        logger.warning(f"DLQ: cannot query tasks — {exc}")
        return 0

    if not tasks:
        return 0

    retried = 0
    for task in tasks:
        if task.retry_count >= task.max_retries:
            # Exhausted — move to dead_letter
            try:
                async with async_session() as db:
                    await TaskRepository.update_status(
                        db, task.id, status="dead_letter",
                        error_message=task.error_message or "Max retries exceeded",
                    )
                await _publish_task_event(task.id, "dead_letter")
                logger.info(f"DLQ: task {task.id[:8]} → dead_letter ({task.tool_name})")
            except Exception as exc:
                logger.error(f"DLQ: failed to mark dead_letter {task.id[:8]} — {exc}")
            continue

        handler = _retry_registry.get(task.tool_name)
        if handler is None:
            logger.warning(f"DLQ: no retry handler for '{task.tool_name}', skipping")
            continue

        # Attempt retry
        t0 = time.perf_counter()
        try:
            success, msg = await handler(**(task.payload or {}))
        except Exception as exc:
            success, msg = False, str(exc)

        latency = round((time.perf_counter() - t0) * 1000, 2)
        retried += 1

        try:
            async with async_session() as db:
                if success:
                    await TaskRepository.update_status(
                        db, task.id, status="completed",
                        result={"message": msg, "latency_ms": latency},
                    )
                    await _publish_task_event(task.id, "completed")
                    logger.info(f"DLQ: retry OK — {task.tool_name} ({latency}ms)")
                else:
                    updated = await TaskRepository.increment_retry(db, task.id)
                    await _publish_task_event(
                        task.id,
                        "dead_letter" if (updated and updated.status == "dead_letter") else "failed",
                    )
                    logger.warning(
                        f"DLQ: retry failed — {task.tool_name} "
                        f"(attempt {task.retry_count + 1}/{task.max_retries}): {msg[:120]}"
                    )
        except Exception as exc:
            logger.error(f"DLQ: DB update failed for {task.id[:8]} — {exc}")

    return retried


async def _publish_task_event(task_id: str, status: str) -> None:
    """Push a task_update event to the EventBus for Dashboard subscribers."""
    try:
        await event_bus.publish("task_update", {
            "task_id": task_id,
            "status": status,
        })
    except Exception:
        pass
