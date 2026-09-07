"""Persists CAMERA_ONLINE/CAMERA_OFFLINE events to the Camera row's `status`
column. Live status for the dashboard's classroom view comes straight from
the running CameraWorker (see routes_classrooms.py), but `GET /api/cameras`
reads the DB directly — without this subscriber that list would show
whatever `status` a camera had at creation time forever, out of sync with
reality."""
from __future__ import annotations

import logging

from sqlalchemy.ext.asyncio import async_sessionmaker

from app.events.event_bus import Event, EventBus
from app.events.event_types import EventType
from app.models.camera import Camera
from app.models.enums import CameraStatus

logger = logging.getLogger(__name__)


class CameraStatusSync:
    def __init__(self, event_bus: EventBus, session_factory: async_sessionmaker) -> None:
        self.event_bus = event_bus
        self.session_factory = session_factory

    def register(self) -> None:
        self.event_bus.subscribe(EventType.CAMERA_ONLINE, self._on_online)
        self.event_bus.subscribe(EventType.CAMERA_OFFLINE, self._on_offline)

    async def _on_online(self, event: Event) -> None:
        await self._set_status(event.payload["camera_id"], CameraStatus.ONLINE)

    async def _on_offline(self, event: Event) -> None:
        await self._set_status(event.payload["camera_id"], CameraStatus.OFFLINE)

    async def _set_status(self, camera_id: str, status: CameraStatus) -> None:
        async with self.session_factory() as session:
            camera = await session.get(Camera, camera_id)
            if camera is not None and camera.status != status.value:
                camera.status = status.value
                await session.commit()
