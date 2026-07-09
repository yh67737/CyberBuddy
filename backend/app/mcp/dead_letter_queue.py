"""Dead Letter Queue (DLQ) — handles failed MCP tool calls.

When an MCP tool call fails due to rate limiting or downtime, the task
enters the async queue for retry. Failed tasks eventually land in the
dead letter queue rather than blocking the user's chat.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Optional


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

    In production, this would be backed by Redis + Celery for persistence
    and distributed workers.
    """

    def __init__(self):
        self._queue: dict[str, DLQTask] = {}

    def enqueue(self, task: DLQTask) -> None:
        """Add a failed task to the queue."""
        self._queue[task.id] = task

    def dequeue(self, task_id: str) -> Optional[DLQTask]:
        """Remove and return a task from the queue."""
        return self._queue.pop(task_id, None)

    def get_pending(self) -> list[DLQTask]:
        """Get all pending tasks ready for retry."""
        return [t for t in self._queue.values() if t.status == DLQTaskStatus.PENDING]

    def mark_dead(self, task_id: str, error: str) -> None:
        """Mark a task as permanently failed (dead letter)."""
        if task_id in self._queue:
            self._queue[task_id].status = DLQTaskStatus.DEAD_LETTER
            self._queue[task_id].last_error = error

    def mark_completed(self, task_id: str) -> None:
        """Mark a task as successfully completed."""
        if task_id in self._queue:
            self._queue[task_id].status = DLQTaskStatus.COMPLETED

    @property
    def dead_count(self) -> int:
        """Number of tasks in dead letter status."""
        return sum(1 for t in self._queue.values() if t.status == DLQTaskStatus.DEAD_LETTER)

    @property
    def pending_count(self) -> int:
        """Number of tasks awaiting retry."""
        return sum(1 for t in self._queue.values() if t.status == DLQTaskStatus.PENDING)


# Global DLQ instance
dead_letter_queue = DeadLetterQueue()
