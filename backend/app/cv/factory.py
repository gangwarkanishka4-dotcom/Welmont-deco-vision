"""Builds CV components from settings — the one place that decides which
concrete implementation backs each interface. Swapping a trained age-group
model in later is just setting AGE_MODEL in .env; nothing else changes."""
from __future__ import annotations

import logging

from app.config import Settings
from app.cv.classifier.base import AgeGroupClassifier
from app.cv.classifier.heuristic_classifier import HeuristicAgeClassifier
from app.cv.detector.base import PersonDetector
from app.cv.pose.base import PoseEstimator
from app.cv.tracker.base import PersonTracker

logger = logging.getLogger(__name__)


def build_detector(settings: Settings) -> PersonDetector:
    from app.cv.detector.yolo_detector import YOLODetector

    return YOLODetector(
        model_path=settings.person_model,
        device=settings.device,
        conf_threshold=settings.detector_conf_threshold,
        iou_threshold=settings.detector_iou_threshold,
        class_ids=settings.detector_class_ids,
    )


def build_pose_estimator(settings: Settings) -> PoseEstimator | None:
    if not settings.pose_model:
        return None
    from app.cv.pose.yolo_pose import YOLOPoseEstimator

    return YOLOPoseEstimator(model_path=settings.pose_model, device=settings.device)


def build_classifier(settings: Settings) -> AgeGroupClassifier:
    if settings.age_model:
        from app.cv.classifier.ml_classifier import MLAgeClassifier

        # Appearance-based (image) model — trained on what a person actually looks
        # like, not pose geometry. Confirmed 94% adult recall vs. the geometry
        # model's 85%, so this now takes priority when configured.
        logger.info("Using trained appearance (image) model: %s", settings.age_model)
        return MLAgeClassifier(model_path=settings.age_model, device=settings.device, input_size=160)

    if settings.trained_feature_classifier_path:
        from app.cv.classifier.trained_feature_classifier import TrainedFeatureClassifier

        logger.info("Using trained feature classifier: %s", settings.trained_feature_classifier_path)
        return TrainedFeatureClassifier(model_path=settings.trained_feature_classifier_path)

    logger.info("No trained classifier configured — using heuristic geometry/pose classifier fallback")
    return HeuristicAgeClassifier()


def build_tracker(settings: Settings) -> PersonTracker:
    from app.cv.tracker.bytetrack_tracker import ByteTrackTracker

    return ByteTrackTracker(track_timeout_seconds=settings.track_timeout_seconds, fps=settings.inference_fps)
