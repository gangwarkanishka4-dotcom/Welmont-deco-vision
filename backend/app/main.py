from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select

from app.api.routes_alerts import router as alerts_router
from app.api.routes_cameras import router as cameras_router
from app.api.routes_classrooms import router as classrooms_router
from app.config import get_settings
from app.core.logging import configure_logging
from app.cv.factory import build_classifier, build_detector, build_pose_estimator
from app.database import AsyncSessionLocal
from app.events.event_bus import get_event_bus
from app.hardware.factory import build_alert_output
from app.models.camera import Camera
from app.models.camera_configuration import CameraConfiguration
from app.models.classroom import Classroom
from app.video.clip_writer import ClipWriter
from app.video.retention import retention_loop
from app.websocket.manager import ConnectionManager
from app.websocket.routes import build_ws_router
from app.workers.bootstrap import start_camera_worker
from app.workers.registry import CameraWorkerRegistry

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    configure_logging(settings.debug_mode)

    event_bus = get_event_bus()
    registry = CameraWorkerRegistry(settings)
    clip_writer = ClipWriter(settings.clip_storage_dir, settings.video_retention_days, settings.inference_fps)
    ws_manager = ConnectionManager(event_bus)
    ws_manager.register()

    from app.alerts.alert_manager import AlertManager

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

    app.state.settings = settings
    app.state.event_bus = event_bus
    app.state.registry = registry
    app.state.clip_writer = clip_writer
    app.state.alert_manager = alert_manager
    app.state.ws_manager = ws_manager
    app.state.detector = detector
    app.state.classifier = classifier
    app.state.pose_estimator = pose_estimator

    app.include_router(build_ws_router(ws_manager))

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
    logger.info("Started %d camera worker(s)", len(registry.all()))

    retention_task = asyncio.create_task(retention_loop(AsyncSessionLocal))

    yield

    retention_task.cancel()
    await registry.stop_all()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="Classroom Supervision & Intrusion Detection", version="1.0.0", lifespan=lifespan)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(cameras_router)
    app.include_router(alerts_router)
    app.include_router(classrooms_router)

    # Serves incident clips (Alert.clip_url points at /media/clips/<alert_id>.mp4)
    # so the dashboard's "View Clip" player can load them directly.
    settings.ensure_storage_dirs()
    app.mount("/media/clips", StaticFiles(directory=settings.clip_storage_dir), name="clips")

    @app.get("/api/health")
    async def health() -> dict:
        return {"status": "ok"}

    return app


app = create_app()
