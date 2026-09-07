from __future__ import annotations

import asyncio
import logging

import cv2
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.crypto import decrypt_secret, encrypt_secret
from app.database import get_db
from app.models.camera import Camera
from app.models.camera_configuration import CameraConfiguration
from app.models.classroom import Classroom
from app.schemas.camera import (
    CameraCalibrationUpdate,
    CameraConfigurationOut,
    CameraCreate,
    CameraOut,
    CameraROIUpdate,
    CameraUpdate,
)
from app.workers.bootstrap import start_camera_worker

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/cameras", tags=["cameras"])


@router.get("", response_model=list[CameraOut])
async def list_cameras(db: AsyncSession = Depends(get_db)) -> list[Camera]:
    return list((await db.scalars(select(Camera))).all())


@router.post("", response_model=CameraOut, status_code=201)
async def create_camera(payload: CameraCreate, request: Request, db: AsyncSession = Depends(get_db)) -> Camera:
    classroom = await db.get(Classroom, payload.classroom_id)
    if classroom is None:
        raise HTTPException(404, "Classroom not found")

    camera = Camera(
        name=payload.name,
        classroom_id=payload.classroom_id,
        rtsp_host=payload.rtsp_host,
        rtsp_port=payload.rtsp_port,
        rtsp_path=payload.rtsp_path,
        rtsp_username=payload.rtsp_username,
        rtsp_password_encrypted=encrypt_secret(payload.rtsp_password) if payload.rtsp_password else "",
        fps=payload.fps,
        resolution_width=payload.resolution_width,
        resolution_height=payload.resolution_height,
        enabled=payload.enabled,
    )
    db.add(camera)
    await db.flush()
    db.add(CameraConfiguration(camera_id=camera.id))
    await db.commit()
    await db.refresh(camera)

    if camera.enabled:
        _start_worker(request, camera, classroom.name, None)

    return camera


@router.put("/{camera_id}", response_model=CameraOut)
async def update_camera(camera_id: str, payload: CameraUpdate, request: Request, db: AsyncSession = Depends(get_db)) -> Camera:
    camera = await db.get(Camera, camera_id)
    if camera is None:
        raise HTTPException(404, "Camera not found")

    data = payload.model_dump(exclude_unset=True, exclude={"rtsp_password"})
    for field, value in data.items():
        setattr(camera, field, value)
    if payload.rtsp_password:
        camera.rtsp_password_encrypted = encrypt_secret(payload.rtsp_password)

    await db.commit()
    await db.refresh(camera)

    # restart the worker so connection/ROI/credential changes take effect immediately
    registry = request.app.state.registry
    await registry.remove(camera_id)
    if camera.enabled:
        classroom = await db.get(Classroom, camera.classroom_id)
        config = await db.scalar(select(CameraConfiguration).where(CameraConfiguration.camera_id == camera_id))
        _start_worker(request, camera, classroom.name, config)

    return camera


@router.delete("/{camera_id}", status_code=204)
async def delete_camera(camera_id: str, request: Request, db: AsyncSession = Depends(get_db)) -> None:
    camera = await db.get(Camera, camera_id)
    if camera is None:
        raise HTTPException(404, "Camera not found")
    await request.app.state.registry.remove(camera_id)
    await db.delete(camera)
    await db.commit()


@router.post("/{camera_id}/enable", response_model=CameraOut)
async def enable_camera(camera_id: str, request: Request, db: AsyncSession = Depends(get_db)) -> Camera:
    camera = await db.get(Camera, camera_id)
    if camera is None:
        raise HTTPException(404, "Camera not found")
    camera.enabled = True
    await db.commit()
    await db.refresh(camera)
    if request.app.state.registry.get(camera_id) is None:
        classroom = await db.get(Classroom, camera.classroom_id)
        config = await db.scalar(select(CameraConfiguration).where(CameraConfiguration.camera_id == camera_id))
        _start_worker(request, camera, classroom.name, config)
    return camera


@router.post("/{camera_id}/disable", response_model=CameraOut)
async def disable_camera(camera_id: str, request: Request, db: AsyncSession = Depends(get_db)) -> Camera:
    camera = await db.get(Camera, camera_id)
    if camera is None:
        raise HTTPException(404, "Camera not found")
    camera.enabled = False
    await db.commit()
    await db.refresh(camera)
    await request.app.state.registry.remove(camera_id)
    return camera


@router.post("/{camera_id}/test")
async def test_camera(camera_id: str, db: AsyncSession = Depends(get_db)) -> dict:
    """Briefly opens the RTSP stream to confirm connectivity — independent of
    whether a live worker is currently running for this camera."""
    camera = await db.get(Camera, camera_id)
    if camera is None:
        raise HTTPException(404, "Camera not found")

    password = decrypt_secret(camera.rtsp_password_encrypted) if camera.rtsp_password_encrypted else ""
    url = camera.build_rtsp_url(password)

    def _try_open() -> tuple[bool, str]:
        cap = cv2.VideoCapture(url)
        try:
            if not cap.isOpened():
                return False, "Could not open RTSP stream"
            ok, _ = cap.read()
            return (True, "OK") if ok else (False, "Stream opened but no frame received")
        finally:
            cap.release()

    success, message = await asyncio.to_thread(_try_open)
    return {"success": success, "message": message}


@router.get("/{camera_id}/stream")
async def stream_camera(camera_id: str, request: Request):
    """MJPEG live view (the overlay-annotated frame this camera's worker most
    recently processed) — good enough for the dashboard's <img>/live tile or
    modal without standing up a full WebRTC/HLS stack."""
    worker = request.app.state.registry.get(camera_id)
    if worker is None:
        raise HTTPException(404, "Camera is not running")

    async def generate():
        while True:
            jpeg = worker.render_overlay_jpeg()
            if jpeg is not None:
                yield b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + jpeg + b"\r\n"
            await asyncio.sleep(1.0 / 12)

    return StreamingResponse(generate(), media_type="multipart/x-mixed-replace; boundary=frame")


@router.post("/{camera_id}/roi", response_model=CameraConfigurationOut)
async def set_roi(camera_id: str, payload: CameraROIUpdate, request: Request, db: AsyncSession = Depends(get_db)) -> CameraConfigurationOut:
    config = await db.scalar(select(CameraConfiguration).where(CameraConfiguration.camera_id == camera_id))
    if config is None:
        raise HTTPException(404, "Camera configuration not found")
    config.roi_polygon = [p.model_dump() for p in payload.roi]
    await db.commit()
    await db.refresh(config)

    worker = request.app.state.registry.get(camera_id)
    if worker is not None:
        worker.calibration.roi_polygon = [(p.x, p.y) for p in payload.roi]

    return _config_out(config)


@router.post("/{camera_id}/calibration", response_model=CameraConfigurationOut)
async def set_calibration(camera_id: str, payload: CameraCalibrationUpdate, request: Request, db: AsyncSession = Depends(get_db)) -> CameraConfigurationOut:
    config = await db.scalar(select(CameraConfiguration).where(CameraConfiguration.camera_id == camera_id))
    if config is None:
        raise HTTPException(404, "Camera configuration not found")

    config.calibration_points = [p.model_dump() for p in payload.calibration_points]
    if payload.adult_height_ratio is not None:
        config.adult_height_ratio = payload.adult_height_ratio
    if payload.child_height_ratio is not None:
        config.child_height_ratio = payload.child_height_ratio
    await db.commit()
    await db.refresh(config)

    worker = request.app.state.registry.get(camera_id)
    if worker is not None:
        worker.calibration = config.to_calibration()

    return _config_out(config)


@router.get("/{camera_id}/configuration", response_model=CameraConfigurationOut)
async def get_configuration(camera_id: str, db: AsyncSession = Depends(get_db)) -> CameraConfigurationOut:
    config = await db.scalar(select(CameraConfiguration).where(CameraConfiguration.camera_id == camera_id))
    if config is None:
        raise HTTPException(404, "Camera configuration not found")
    return _config_out(config)


def _config_out(config: CameraConfiguration) -> CameraConfigurationOut:
    return CameraConfigurationOut(
        camera_id=config.camera_id,
        roi=config.roi_polygon,
        calibration_points=config.calibration_points,
        adult_height_ratio=config.adult_height_ratio,
        child_height_ratio=config.child_height_ratio,
    )


def _start_worker(request: Request, camera: Camera, classroom_name: str, config: CameraConfiguration | None) -> None:
    state = request.app.state
    start_camera_worker(
        camera=camera,
        configuration=config,
        classroom_name=classroom_name,
        settings=state.settings,
        event_bus=state.event_bus,
        clip_writer=state.clip_writer,
        registry=state.registry,
        detector=state.detector,
        classifier=state.classifier,
        pose_estimator=state.pose_estimator,
    )
