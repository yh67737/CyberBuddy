"""In-process async event bus for real-time dashboard push.

A lightweight pub/sub built on asyncio.Queue. Subscribes listeners to typed
events and delivers messages to all registered queues. Can be swapped for
Redis pubsub later by implementing the same interface.

Event types:
  - new_incident:    Fired when SecurityGuardian creates a SecurityIncident
  - incident_update: Fired when an incident status changes
  - task_update:     Fired when an async MCP task status changes
"""

import asyncio
from collections import defaultdict
from typing import Any

from loguru import logger


class EventBus:
    """In-memory publish/subscribe event bus with queue-per-subscriber."""

    def __init__(self) -> None:
        self._subscribers: dict[str, set[asyncio.Queue]] = defaultdict(set)

    def subscribe(self, event_type: str, queue: asyncio.Queue) -> None:
        """Register a queue to receive events of the given type."""
        self._subscribers[event_type].add(queue)
        logger.debug(
            f"EventBus: +subscriber for '{event_type}' "
            f"(total: {len(self._subscribers[event_type])})"
        )

    def unsubscribe(self, event_type: str, queue: asyncio.Queue) -> None:
        """Remove a queue from event type subscriptions."""
        self._subscribers[event_type].discard(queue)
        remaining = len(self._subscribers[event_type])
        if remaining == 0:
            del self._subscribers[event_type]
        logger.debug(
            f"EventBus: -subscriber for '{event_type}' (remaining: {remaining})"
        )

    async def publish(self, event_type: str, data: dict[str, Any]) -> None:
        """Publish an event to all subscribers of that type.

        Non-blocking: each subscriber queue gets the message via put_nowait.
        Full queues are dropped and the subscriber is cleaned up.
        """
        queues = self._subscribers.get(event_type, set())
        if not queues:
            return

        message = {"type": event_type, **data}
        dead_queues: set[asyncio.Queue] = set()

        for queue in queues:
            try:
                queue.put_nowait(message)
            except asyncio.QueueFull:
                logger.warning(
                    f"EventBus: subscriber queue full for '{event_type}', "
                    f"dropping message and removing subscriber"
                )
                dead_queues.add(queue)

        for q in dead_queues:
            self._subscribers[event_type].discard(q)

    @property
    def subscriber_count(self) -> dict[str, int]:
        """Return counts of subscribers per event type (for debugging)."""
        return {k: len(v) for k, v in self._subscribers.items()}


# Global singleton — imported wherever events are published or consumed
event_bus = EventBus()
