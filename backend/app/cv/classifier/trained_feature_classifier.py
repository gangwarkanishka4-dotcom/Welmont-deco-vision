"""Adult/child classifier backed by the RandomForest trained in ml_pipeline/
(see ml_pipeline/3_train_model.py and ml_pipeline/integration_snippet.py,
which this mirrors). Unlike ml_classifier.py's MLAgeClassifier, this doesn't
take raw pixels — it takes the same hand-engineered pose features
(shoulder/head width, build ratio, leg extension, box height) the heuristic
classifier already computes, so it's a drop-in replacement for that scoring
step specifically. Tracking, gate-crossing counts, and
RollingClassificationHistory's temporal smoothing are all unaffected — they
only see the resulting adult_score, same as with the heuristic.

Loads the .onnx export (not the .joblib directly): this backend's venv can't
import scikit-learn/scipy — an Application Control policy on this machine
blocks scipy's compiled extensions from a Desktop-tree path — but
onnxruntime is already a pinned dependency here and works fine. Retraining
in ml_pipeline/ (3_train_model.py) regenerates both files together; always
point trained_feature_classifier_path at the .onnx one.

Falls back to HeuristicAgeClassifier whenever pose features aren't
available (shoulders not confidently detected — occlusion, awkward angle,
bent over). The trained model has no signal at all without pose, unlike the
heuristic (which also has geometry/appearance signals) — without this
fallback, a person whose pose keeps failing sits at a flat neutral score
forever and never gets classified as anything, which is worse than a
possibly-wrong heuristic guess.
"""
from __future__ import annotations

import logging
import math

import numpy as np
import onnxruntime as ort

from app.cv.calibration.roi import CameraCalibration
from app.cv.classifier.base import AgeGroupClassifier, FrameClassification
from app.cv.classifier.heuristic_classifier import HeuristicAgeClassifier
from app.cv.detector.base import Detection
from app.cv.pose.base import PoseResult

logger = logging.getLogger(__name__)

# Must match NUMERIC_FEATURE_COLUMNS in ml_pipeline/3_train_model.py, same
# order — the ONNX graph's input columns are positional, not named.
FEATURE_ORDER = ["shoulder_width", "head_width", "build_ratio", "leg_to_upper_ratio", "box_height", "detector_confidence"]


class TrainedFeatureClassifier(AgeGroupClassifier):
    def __init__(self, model_path: str) -> None:
        self.session = ort.InferenceSession(model_path, providers=["CPUExecutionProvider"])
        self.input_name = self.session.get_inputs()[0].name
        self.fallback = HeuristicAgeClassifier()
        logger.info("Loaded trained feature classifier from %s", model_path)

    def classify(
        self,
        frame: np.ndarray,
        detection: Detection,
        pose: PoseResult | None,
        calibration: CameraCalibration,
    ) -> FrameClassification:
        features = self._extract_features(detection, pose)
        if features is None:
            fallback_result = self.fallback.classify(frame, detection, pose, calibration)
            signals = dict(fallback_result.signals)
            signals["fallback_reason"] = "no_pose_features"
            return FrameClassification(adult_score=fallback_result.adult_score, signals=signals)

        row = np.array([[features[col] for col in FEATURE_ORDER]], dtype=np.float32)
        # Two outputs: [0] class label, [1] probabilities shaped (N, 2) as [P(child), P(adult)].
        _, probabilities = self.session.run(None, {self.input_name: row})
        adult_probability = float(probabilities[0][1])
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
