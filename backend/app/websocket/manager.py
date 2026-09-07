"""Bridges the internal EventBus to connected WebSocket clients. This is the
only thing that turns a confirmed UNSUPERVISED_DETECTED (backend event) into
something the React dashboard sees — no polling anywhere in this path."""
from __future__ import annotations

import logging

from fastapi import WebSocket

from app.events.event_bus import Event, EventBus
from app.events.event_types import EventType

logger = logging.getLogger(__name__)

# Everything the dashboard needs live. TRACKED_STATE_UPDATE is high-frequency
# (per processed frame, per camera) and only matters to a client with the
# live-monitoring modal open — but broadcasting it to all connections is
# still cheap at this scale (single-digit cameras); shard by camera_id first
# if this needs to scale to many concurrent viewers.
BROADCAST_EVENTS = [
    EventType.ALERT_CREATED,
    EventType.ALERT_ACKNOWLEDGED,
    EventType.ALERT_RESOLVED,
    EventType.BUZZER_TRIGGERED,
    EventType.BUZZER_CLEARED,
    EventType.CAMERA_OFFLINE,
    EventType.CAMERA_ONLINE,
    EventType.CLASSROOM_STATUS_CHANGED,
    EventType.TRACKED_STATE_UPDATE,
]


class ConnectionManager:
    def __init__(self, event_bus: EventBus) -> None:
        self.event_bus = event_bus
        self._connections: set[WebSocket] = set()

    def register(self) -> None:
        for event_type in BROADCAST_EVENTS:
            self.event_bus.subscribe(event_type, self._on_event)

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        self._connections.add(websocket)
        logger.info("WebSocket client connected (%d total)", len(self._connections))

    def disconnect(self, websocket: WebSocket) -> None:
        self._connections.discard(websocket)
        logger.info("WebSocket client disconnected (%d total)", len(self._connections))

    async def _on_event(self, event: Event) -> None:
        if not self._connections:
            return
        message = event.to_json()
        dead: list[WebSocket] = []
        for ws in self._connections:
            try:
                await ws.send_text(message)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws)
