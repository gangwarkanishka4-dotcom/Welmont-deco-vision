"""Starts a CameraWorker for one Camera row. Detector/pose/classifier model
instances are built once at app startup and shared across every camera
(reloading YOLO weights per camera would waste GPU/CPU memory and startup
time); only the tracker is per-camera, since track ID spaces must not mix
between cameras."""
from __future__ import annotations

from app.config import Settings
from app.core.crypto import decrypt_secret
from app.cv.calibration.roi import CameraCalibration
from app.cv.classifier.base import AgeGroupClassifier
from app.cv.detector.base import PersonDetector
from app.cv.factory import build_tracker
from app.cv.pose.base import PoseEstimator
from app.events.event_bus import EventBus
from app.models.camera import Camera
from app.models.camera_configuration import CameraConfiguration
from app.video.clip_writer import ClipWriter
from app.workers.pipeline import CameraWorker
from app.workers.registry import CameraWorkerRegistry


def start_camera_worker(
    camera: Camera,
    configuration: CameraConfiguration | None,
    classroom_name: str,
    settings: Settings,
    event_bus: EventBus,
    clip_writer: ClipWriter,
    registry: CameraWorkerRegistry,
    detector: PersonDetector,
    classifier: AgeGroupClassifier,
    pose_estimator: PoseEstimator | None,
) -> CameraWorker:
    calibration = configuration.to_calibration() if configuration else CameraCalibration(camera_id=camera.id)
    password = decrypt_secret(camera.rtsp_password_encrypted) if camera.rtsp_password_encrypted else ""
    rtsp_url = camera.build_rtsp_url(password)

    worker = CameraWorker(
        camera_id=camera.id,
        classroom_id=camera.classroom_id,
        classroom_name=classroom_name,
        rtsp_url=rtsp_url,
        fps=camera.fps,
        settings=settings,
        event_bus=event_bus,
        detector=detector,
        tracker=build_tracker(settings),
        classifier=classifier,
        calibration=calibration,
        clip_writer=clip_writer,
        pose_estimator=pose_estimator,
    )
    registry.add(worker)
    return worker
