"""Fallback adult/child classifier: no trained model required.

Combines three independent signals into one adult-likeness score:

  1. geometry  — calibrated height ratio (detection height vs the expected
                 adult height at that row of the frame, from the camera's
                 perspective calibration). This replaces a naive global
                 pixel-height threshold.
  2. pose      — two body-proportion ratios from keypoints (shoulders/ears/
                 hips/knees/ankles) plus the detection box's own top edge as
                 a head-length fallback, deliberately not the nose/eyes — a
                 preschooler is rarely facing the camera (constantly moving,
                 looking down, turned away, or simply seen from behind on a
                 ceiling-mounted camera), so requiring a frontal face
                 keypoint would drop this signal on most real frames:

                   a) shoulder-width to head-width. Head width prefers
                      ear-to-ear distance (COCO keypoints estimate ear
                      position even from behind, unlike the nose) and falls
                      back to the box-top-to-shoulder-line proxy only when
                      neither ear is confidently visible. A 3-3.5y toddler
                      (average ~95-100cm tall) has a head nearly as wide as
                      their shoulders; an adult (~155-175cm) has shoulders
                      far broader than their head. Unlike (b), this holds
                      whether the person is standing, sitting on the floor,
                      or bent over a desk, and facing the camera or facing
                      away from it — a preschool classroom spends most of the
                      day in exactly those postures.
                   b) leg-length to (head+torso)-length, skipped whenever the
                      knee keypoint shows the leg is bent rather than
                      extended (see _leg_is_extended) — a seated or crouched
                      person's hip-to-ankle distance is foreshortened and
                      says nothing about their real leg length, adult or
                      child.

                 Absolute height alone is a closer call than it looks: at
                 ~95-100cm vs a ~155-175cm adult, the real height ratio is
                 roughly 0.55-0.65 — close enough to blur against a single
                 global threshold, which is why this signal leans on
                 proportion (shape) rather than scale. Approximate by
                 design — meant to be replaced or augmented by a trained
                 model (see MLAgeClassifier).
  3. confidence — the detector's own confidence is used as a *reliability
                 weight* (how much this frame's contribution should count in
                 the rolling history), not as a direction signal, since
                 detection confidence says nothing about age.

If pose is unavailable for a detection (occlusion, low keypoint confidence)
the score falls back to geometry alone. If calibration has no reference
points yet, geometry contributes a neutral 0.5 and the classifier leans
entirely on pose (or returns neutral 0.5/UNKNOWN if neither is available —
which is the correct, honest behavior until an admin calibrates the camera).
"""
from __future__ import annotations

import logging
import math

import numpy as np

from app.cv.calibration.roi import CameraCalibration
from app.cv.classifier.base import AgeGroupClassifier, FrameClassification
from app.cv.detector.base import Detection
from app.cv.pose.base import PoseResult

logger = logging.getLogger(__name__)

GEOMETRY_WEIGHT = 0.6
POSE_WEIGHT = 0.4


def _sigmoid(x: float, midpoint: float, steepness: float) -> float:
    return 1.0 / (1.0 + math.exp(-steepness * (x - midpoint)))


class HeuristicAgeClassifier(AgeGroupClassifier):
    def classify(
        self,
        frame: np.ndarray,
        detection: Detection,
        pose: PoseResult | None,
        calibration: CameraCalibration,
    ) -> FrameClassification:
        signals: dict[str, float] = {}

        geometry_score = self._geometry_score(detection, calibration)
        pose_score = self._pose_score(pose, detection)

        if geometry_score is not None:
            signals["geometry"] = geometry_score
        if pose_score is not None:
            signals["pose"] = pose_score

        if geometry_score is not None and pose_score is not None:
            fused = GEOMETRY_WEIGHT * geometry_score + POSE_WEIGHT * pose_score
        elif geometry_score is not None:
            fused = geometry_score
        elif pose_score is not None:
            fused = pose_score
        else:
            fused = 0.5  # no usable signal this frame — stay neutral, let temporal window decide

        signals["confidence_weight"] = detection.confidence
        signals["fused"] = fused
        return FrameClassification(adult_score=fused, signals=signals)

    def _geometry_score(self, detection: Detection, calibration: CameraCalibration) -> float | None:
        ratio = calibration.height_ratio(detection)
        if ratio is None:
            return None
        # Map the calibrated ratio through a sigmoid centered between the
        # configured adult/child ratio thresholds, so results near either
        # threshold saturate toward 1.0 / 0.0 while the middle stays graded.
        midpoint = (calibration.adult_height_ratio + calibration.child_height_ratio) / 2.0
        span = max(calibration.adult_height_ratio - calibration.child_height_ratio, 1e-3)
        steepness = 6.0 / span
        return _sigmoid(ratio, midpoint, steepness)

    def _pose_score(self, pose: PoseResult | None, detection: Detection) -> float | None:
        if pose is None:
            return None

        left_shoulder = pose.get("left_shoulder")
        right_shoulder = pose.get("right_shoulder")
        if not left_shoulder or not right_shoulder:
            return None

        shoulder = _midpoint(left_shoulder, right_shoulder)
        shoulder_width = _dist(left_shoulder, right_shoulder)
        # Head length from the detection box's own top edge to the shoulder
        # line, not the nose keypoint: a preschooler is rarely posed facing
        # the camera (constantly moving, looking down, turned away), so
        # requiring the nose would drop the pose signal for most real frames.
        # The box top is already produced by the detector for every
        # detection, face visible or not.
        head_len = max(0.0, shoulder[1] - detection.y1)

        scores: list[float] = []

        # Head width from ear-to-ear distance only — verified against this
        # camera's own footage on 2026-09-07 (see POSE_DEBUG log): the
        # ear-based ratio is stable and consistent for the same real people
        # across frames (~1.85-2.5 for adults confirmed in-room), but the
        # box-top-to-shoulder-line fallback used previously produced wildly
        # different, much larger numbers (55-82 vs 30-35) for comparable
        # people on this specific lens/mounting angle — likely because the
        # pose model's shoulder keypoint sits lower than expected from this
        # steep downward viewing angle, inflating the "head length" proxy.
        # Rather than feed the classifier a proxy shown to be unreliable
        # here, this signal now goes unavailable (falls through to geometry
        # or neutral) whenever ears aren't confidently detected, instead of
        # guessing from box-top.
        left_ear = pose.get("left_ear")
        right_ear = pose.get("right_ear")
        build_ratio = None
        if left_ear and right_ear:
            head_width = _dist(left_ear, right_ear)
            if shoulder_width > 1e-3 and head_width > 1e-3:
                # Shoulder-width-to-head-width: a 3-3.5y toddler's head is
                # nearly as wide as their shoulders; an adult's shoulders are
                # far broader than their head. Holds whether the person is
                # standing, sitting on the floor, or bent over a desk, and
                # facing the camera or away from it.
                build_ratio = shoulder_width / head_width
                scores.append(_sigmoid(build_ratio, midpoint=1.5, steepness=3.5))

        hip = _midpoint(pose.get("left_hip"), pose.get("right_hip"))
        ankle = _midpoint(pose.get("left_ankle"), pose.get("right_ankle"))
        knee = _midpoint(pose.get("left_knee"), pose.get("right_knee"))

        # Leg-length ratio: DISABLED as a scored signal as of 2026-09-07 —
        # same footage showed leg_to_upper_ratio consistently reading low
        # (child-like) for people the shoulder/ear signal read confidently
        # as adult, even when the bent-knee check reported the leg as
        # extended. On this camera it was pulling correct ear-based reads
        # toward wrong labels more often than it corroborated them. Still
        # computed and logged so it can be re-validated and re-enabled once
        # understood, just not averaged into the score for now.
        leg_to_upper_ratio = None
        leg_extended = None
        if hip and ankle:
            leg_extended = _leg_is_extended(hip, knee, ankle)
            if leg_extended:
                torso_len = _dist(shoulder, hip)
                leg_len = _dist(hip, ankle)
                upper_body = torso_len + head_len
                if upper_body > 1e-3:
                    leg_to_upper_ratio = leg_len / upper_body

        logger.debug(
            "POSE_DEBUG shoulder_w=%.1f ears=%s build_ratio=%s hip=%s ankle=%s leg_extended=%s "
            "leg_ratio=%s(unscored) scores=%s",
            shoulder_width,
            bool(left_ear and right_ear),
            f"{build_ratio:.2f}" if build_ratio is not None else None,
            hip is not None,
            ankle is not None,
            leg_extended,
            f"{leg_to_upper_ratio:.2f}" if leg_to_upper_ratio is not None else None,
            [round(s, 2) for s in scores],
        )

        if not scores:
            return None
        return sum(scores) / len(scores)


def _leg_is_extended(hip: tuple[float, float], knee: tuple[float, float] | None, ankle: tuple[float, float]) -> bool:
    """True if the leg reads as roughly straight (standing) rather than bent
    (sitting cross-legged, crouching, kneeling). Without a confident knee
    keypoint there's no way to check, so the leg ratio gets the benefit of
    the doubt rather than being discarded outright."""
    if knee is None:
        return True
    direct = _dist(hip, ankle)
    via_knee = _dist(hip, knee) + _dist(knee, ankle)
    if via_knee <= 1e-3:
        return True
    return (direct / via_knee) > 0.9


def _midpoint(a: tuple[float, float] | None, b: tuple[float, float] | None) -> tuple[float, float] | None:
    if a and b:
        return ((a[0] + b[0]) / 2.0, (a[1] + b[1]) / 2.0)
    return a or b


def _dist(a: tuple[float, float] | None, b: tuple[float, float] | None) -> float:
    if not a or not b:
        return 0.0
    return math.hypot(a[0] - b[0], a[1] - b[1])
