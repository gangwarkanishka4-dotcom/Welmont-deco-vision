"""Standalone CV worker process — an alternative to the default all-in-one
`app.main` for the split deployment shown in spec §32:

    Camera -> CV Worker (this process) -> Redis pub/sub -> FastAPI (app.main,
    running with SERVICE_ROLE=api) -> WebSocket -> React / Postgres / Relay

Run with USE_REDIS_EVENTBUS=true and the same DATABASE_URL/REDIS_URL as the
API process so both share the database and event stream. This process owns
every camera worker, the AlertManager, and the buzzer/relay — the API
process only reads the database and relays events, it never mutates live
camera/tracker state directly in split mode (see README "Running as split
processes" for the current limitation on live camera CRUD in this mode).

For most deployments the default single-process `app.main` (SERVICE_ROLE=all,
the docker-compose default) is simpler and is the fully tested configuration;
use this only if you need to scale the API/WebSocket layer independently of
CV inference.
"""
from __future__ import annotations

import asyncio
import logging

from sqlalchemy import select

from app.alerts.alert_manager import AlertManager
from app.config import get_settings
from app.core.logging import configure_logging
from app.cv.factory import build_classifier, build_detector, build_pose_estimator
from app.database import AsyncSessionLocal
from app.events.event_bus import EventBus, RedisEventBus
from app.hardware.factory import build_alert_output
from app.models.camera import Camera
from app.models.camera_configuration import CameraConfiguration
from app.models.classroom import Classroom
from app.video.clip_writer import ClipWriter
from app.video.retention import retention_loop
from app.workers.bootstrap import start_camera_worker
from app.workers.registry import CameraWorkerRegistry

logger = logging.getLogger(__name__)


async def main() -> None:
    settings = get_settings()
    configure_logging(settings.debug_mode)

    event_bus: EventBus
    if settings.redis_url:
        redis_bus = RedisEventBus(settings.redis_url)
        await redis_bus.start()
        event_bus = redis_bus
    else:
        logger.warning("REDIS_URL not set — running with an in-process event bus (no other process will see these events)")
        event_bus = EventBus()

    registry = CameraWorkerRegistry(settings)
    clip_writer = ClipWriter(settings.clip_storage_dir, settings.video_retention_days, settings.inference_fps)

    alert_manager = AlertManager(
        event_bus=event_bus,
        session_factory=AsyncSessionLocal,
        alert_output=build_alert_output(settings),
        settings=settings,
        media_provider=registry,
    )
    alert_manager.register()

    from app.workers.camera_status_sync import CameraStatusSync

    camera_status_sync = CameraStatusSync(event_bus=event_bus, session_factory=AsyncSessionLocal)
    camera_status_sync.register()

    logger.info("Loading shared CV models (device=%s)...", settings.device)
    detector = build_detector(settings)
    detector.warmup()
    classifier = build_classifier(settings)
    pose_estimator = build_pose_estimator(settings)

    async with AsyncSessionLocal() as session:
        cameras = list((await session.scalars(select(Camera).where(Camera.enabled.is_(True)))).all())
        for camera in cameras:
            classroom = await session.get(Classroom, camera.classroom_id)
            config = await session.scalar(select(CameraConfiguration).where(CameraConfiguration.camera_id == camera.id))
            start_camera_worker(
                camera=camera,
                configuration=config,
                classroom_name=classroom.name if classroom else camera.name,
                settings=settings,
                event_bus=event_bus,
                clip_writer=clip_writer,
                registry=registry,
                detector=detector,
                classifier=classifier,
                pose_estimator=pose_estimator,
            )
    logger.info("CV worker process started with %d camera(s)", len(registry.all()))

    retention_task = asyncio.create_task(retention_loop(AsyncSessionLocal))

    try:
        await asyncio.Event().wait()  # run forever
    finally:
        retention_task.cancel()
        await registry.stop_all()
        if isinstance(event_bus, RedisEventBus):
            await event_bus.stop()


if __name__ == "__main__":
    asyncio.run(main())
