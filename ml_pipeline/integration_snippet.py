"""Step 5: how to swap the trained model in for the rule-based height/pose
scoring, once 3_train_model.py's report looks good enough to trust (see
README.md in this folder for what "good enough" means here).

Unlike the other three files in this folder, this one is NOT standalone —
it's the bridge back into the main backend package, so it imports from
app.cv.* and belongs in backend/app/cv/classifier/ once you're ready to
apply it (copy this file there, or paste the class below into a new file).

What this replaces: HeuristicAgeClassifier's shoulder/head-width geometry
(the "rule-based height/pose scoring"). What this does NOT touch: ByteTrack
tracking, the gate-crossing door counter, RollingClassificationHistory's
temporal smoothing, or the debounce in the supervision state machine — all
of that already treats "adult_score in 0..1" as an opaque input and doesn't
care which classifier produced it.

Feature computation below is intentionally a near-duplicate of
1_collect_features.py's extract_features(), not a shared import — this repo
already reads Detection/PoseResult objects rather than raw keypoint arrays,
so the two are adapted to their own inputs. If you change one, change the
other: the model was trained on the exact features 1_collect_features.py
produces, and predict_proba() is only meaningful if this file hands it the
same features, computed the same way.
"""
from __future__ import annotations

import math
from pathlib import Path

import joblib
import numpy as np

from app.cv.calibration.roi import CameraCalibration
from app.cv.classifier.base import AgeGroupClassifier, FrameClassification
from app.cv.detector.base import Detection
from app.cv.pose.base import PoseResult

# Must match NUMERIC_FEATURE_COLUMNS in 3_train_model.py, same order.
FEATURE_COLUMNS = ["shoulder_width", "head_width", "build_ratio", "leg_to_upper_ratio", "box_height", "detector_confidence"]


class TrainedFeatureClassifier(AgeGroupClassifier):
    """Loads the .joblib file saved by 3_train_model.py (ml_pipeline/data/
    adult_child_model.joblib by default) and calls its predict_proba()
    instead of the rule-based sigmoid scoring. Geometry (ROI calibration)
    and appearance (uniform match) are untouched — this only replaces the
    pose-based signal."""

    def __init__(self, model_path: str) -> None:
        bundle = joblib.load(model_path)
        self.model = bundle["model"]
        self.feature_columns = bundle["feature_columns"]

    def classify(
        self,
        frame: np.ndarray,
        detection: Detection,
        pose: PoseResult | None,
        calibration: CameraCalibration,
    ) -> FrameClassification:
        features = self._extract_features(detection, pose)
        if features is None:
            return FrameClassification(adult_score=0.5, signals={})

        row = [[features[col] for col in self.feature_columns]]
        adult_probability = float(self.model.predict_proba(row)[0][1])  # [:, 1] = P(adult), matches training's y=1
        return FrameClassification(adult_score=adult_probability, signals={"trained_model": adult_probability})

    @staticmethod
    def _extract_features(detection: Detection, pose: PoseResult | None) -> dict | None:
        if pose is None:
            return None

        left_shoulder, right_shoulder = pose.get("left_shoulder"), pose.get("right_shoulder")
        if not left_shoulder or not right_shoulder:
            return None
        shoulder = _midpoint(left_shoulder, right_shoulder)
        shoulder_width = _dist(left_shoulder, right_shoulder)

        left_ear, right_ear = pose.get("left_ear"), pose.get("right_ear")
        if left_ear and right_ear:
            head_width = _dist(left_ear, right_ear)
        else:
            head_width = max(0.0, shoulder[1] - detection.y1)
        build_ratio = (shoulder_width / head_width) if (shoulder_width > 1e-3 and head_width > 1e-3) else 0.0

        hip = _midpoint(pose.get("left_hip"), pose.get("right_hip"))
        knee = _midpoint(pose.get("left_knee"), pose.get("right_knee"))
        ankle = _midpoint(pose.get("left_ankle"), pose.get("right_ankle"))
        leg_to_upper_ratio = 0.0
        if hip and ankle and _leg_is_extended(hip, knee, ankle):
            head_len = max(0.0, shoulder[1] - detection.y1)
            torso_len = _dist(shoulder, hip)
            leg_len = _dist(hip, ankle)
            upper_body = torso_len + head_len
            if upper_body > 1e-3:
                leg_to_upper_ratio = leg_len / upper_body

        return {
            "shoulder_width": shoulder_width,
            "head_width": head_width,
            "build_ratio": build_ratio,
            "leg_to_upper_ratio": leg_to_upper_ratio,
            "box_height": detection.height,
            "detector_confidence": detection.confidence,
        }


def _midpoint(a, b):
    if a and b:
        return (a[0] + b[0]) / 2.0, (a[1] + b[1]) / 2.0
    return a or b


def _dist(a, b) -> float:
    if not a or not b:
        return 0.0
    return math.hypot(a[0] - b[0], a[1] - b[1])


def _leg_is_extended(hip, knee, ankle) -> bool:
    if knee is None:
        return True
    direct = _dist(hip, ankle)
    via_knee = _dist(hip, knee) + _dist(knee, ankle)
    if via_knee <= 1e-3:
        return True
    return (direct / via_knee) > 0.9


# ============================================================================
# The actual change to app/cv/factory.py — shown as a diff, not applied here.
# Everything else in factory.py (build_detector, build_pose_estimator,
# build_tracker) stays exactly as-is.
# ============================================================================
#
#  def build_classifier(settings: Settings) -> AgeGroupClassifier:
#      if settings.age_model:
#          from app.cv.classifier.ml_classifier import MLAgeClassifier
#          logger.info("Using trained age-group model: %s", settings.age_model)
#          return MLAgeClassifier(model_path=settings.age_model, device=settings.device)
#
# -    logger.info("No AGE_MODEL configured — using heuristic geometry/pose classifier fallback")
# -    return HeuristicAgeClassifier()
# +    trained_feature_model = Path("ml_pipeline/data/adult_child_model.joblib")
# +    if trained_feature_model.exists():
# +        from app.cv.classifier.trained_feature_classifier import TrainedFeatureClassifier
# +        logger.info("Using trained feature classifier: %s", trained_feature_model)
# +        return TrainedFeatureClassifier(model_path=str(trained_feature_model))
# +
# +    logger.info("No trained classifier found — using heuristic geometry/pose classifier fallback")
# +    return HeuristicAgeClassifier()
