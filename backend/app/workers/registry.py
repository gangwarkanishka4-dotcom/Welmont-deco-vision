"""Holds the live CameraWorker instances keyed by camera_id. This is the one
place the API layer (live snapshot, ROI preview, per-camera debug stats) and
AlertManager (via the MediaProvider protocol) reach into the running CV
pipeline — everything else talks through the event bus."""
from __future__ import annotations

import asyncio
import logging

from app.config import Settings
from app.workers.pipeline import CameraWorker

logger = logging.getLogger(__name__)


class CameraWorkerRegistry:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._workers: dict[str, CameraWorker] = {}
        self._tasks: dict[str, asyncio.Task] = {}

    def add(self, worker: CameraWorker) -> None:
        self._workers[worker.camera_id] = worker
        self._tasks[worker.camera_id] = asyncio.create_task(worker.run())
        logger.info("Started camera worker %s", worker.camera_id)

    def get(self, camera_id: str) -> CameraWorker | None:
        return self._workers.get(camera_id)

    def all(self) -> list[CameraWorker]:
        return list(self._workers.values())

    async def remove(self, camera_id: str) -> None:
        worker = self._workers.pop(camera_id, None)
        task = self._tasks.pop(camera_id, None)
        if worker:
            worker.stop()
        if task:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

    async def stop_all(self) -> None:
        for camera_id in list(self._workers.keys()):
            await self.remove(camera_id)

    # MediaProvider protocol --------------------------------------------
    async def capture_snapshot(self, camera_id: str, alert_id: str) -> str | None:
        worker = self._workers.get(camera_id)
        if worker is None:
            return None
        return await worker.capture_snapshot(alert_id, self.settings.snapshot_storage_dir)

    async def request_incident_clip(self, camera_id: str, alert_id: str) -> None:
        worker = self._workers.get(camera_id)
        if worker is not None:
            worker.request_incident_clip(alert_id)
