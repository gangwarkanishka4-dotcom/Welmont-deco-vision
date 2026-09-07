"""In-process async pub/sub event bus. This is the seam that keeps the CV
engine, database, WebSocket layer, and hardware layer decoupled — none of
them import each other directly, they only publish/subscribe to events.

Single-process deployments use this directly. For a multi-worker deployment,
RedisEventBus (below) fans the same events out over Redis pub/sub so every
FastAPI replica sees every event; swap it in via the same interface.
"""
from __future__ import annotations

import asyncio
import json
import logging
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable

from app.events.event_types import EventType

logger = logging.getLogger(__name__)

Handler = Callable[["Event"], Awaitable[None]]


@dataclass
class Event:
    type: EventType
    payload: dict[str, Any] = field(default_factory=dict)
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_json(self) -> str:
        return json.dumps({"type": self.type.value, "payload": self.payload, "timestamp": self.timestamp})


class EventBus:
    def __init__(self) -> None:
        self._handlers: dict[EventType, list[Handler]] = defaultdict(list)

    def subscribe(self, event_type: EventType, handler: Handler) -> None:
        self._handlers[event_type].append(handler)

    def unsubscribe(self, event_type: EventType, handler: Handler) -> None:
        self._handlers[event_type] = [h for h in self._handlers[event_type] if h is not handler]

    async def publish(self, event: Event) -> None:
        handlers = self._handlers.get(event.type, [])
        if not handlers:
            return
        results = await asyncio.gather(*(h(event) for h in handlers), return_exceptions=True)
        for result in results:
            if isinstance(result, Exception):
                logger.exception("Event handler raised for %s", event.type, exc_info=result)

    def publish_sync(self, event: Event) -> None:
        """Fire-and-forget publish from non-async contexts (e.g. the CV worker's
        tight processing loop) — schedules the coroutine on the running loop."""
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(self.publish(event))
        except RuntimeError:
            asyncio.run(self.publish(event))


class RedisEventBus(EventBus):
    """Fans events out over Redis pub/sub so multiple processes (e.g. a
    dedicated CV worker process plus one or more API/WebSocket replicas, per
    the spec §32 preferred architecture) all observe the same event stream.
    Local subscribe()/publish() semantics are unchanged — publish() also
    forwards to Redis, and a background listener re-publishes anything
    received from Redis (including from other processes) to local handlers.
    """

    CHANNEL = "classroom-monitor:events"

    def __init__(self, redis_url: str) -> None:
        super().__init__()
        import redis.asyncio as redis

        self._redis_url = redis_url
        self._redis = redis.from_url(redis_url)
        self._listener_task: asyncio.Task | None = None

    async def start(self) -> None:
        self._listener_task = asyncio.create_task(self._listen())

    async def stop(self) -> None:
        if self._listener_task:
            self._listener_task.cancel()
            try:
                await self._listener_task
            except asyncio.CancelledError:
                pass
        await self._redis.aclose()

    async def publish(self, event: Event) -> None:
        # Only forward to local handlers directly when NOT relayed via Redis —
        # otherwise publish to Redis and let the listener loop deliver it
        # locally too, so every process (including this one) sees exactly one
        # consistent delivery order.
        await self._redis.publish(self.CHANNEL, event.to_json())

    async def _listen(self) -> None:
        pubsub = self._redis.pubsub()
        await pubsub.subscribe(self.CHANNEL)
        try:
            async for message in pubsub.listen():
                if message["type"] != "message":
                    continue
                try:
                    data = json.loads(message["data"])
                    event = Event(type=EventType(data["type"]), payload=data["payload"], timestamp=data["timestamp"])
                except Exception:
                    logger.exception("Failed to decode event from Redis pub/sub")
                    continue
                await super().publish(event)
        finally:
            await pubsub.unsubscribe(self.CHANNEL)


_bus: EventBus | None = None


def get_event_bus() -> EventBus:
    """In-process bus for the default single-process deployment. For a
    split API/worker deployment, construct RedisEventBus explicitly (see
    app/worker_main.py) instead of calling this."""
    global _bus
    if _bus is None:
        _bus = EventBus()
    return _bus
