"""Fallback adult/child classifier: no trained model required.

Combines up to five independent signals into one adult-likeness score,
weight-averaged over whichever are available this frame:

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
  3. relative    — this detection's own pixel height against a rolling, per-
     height       camera reference built from recent detections (no ROI/
                 calibration step required, unlike (1) — added 2026-09-08
                 because real deployments may never get calibrated, leaving
                 geometry permanently silent). A robust low percentile of
                 recent heights should track "94-99cm in pixels" closely as
                 long as this classroom's known children are the majority
                 of what the camera sees, making a notably taller detection
                 (real ratio ~1.4-1.9x) strong evidence of an adult even
                 when pose/appearance are ambiguous or unavailable that
                 frame. Both the reference and the detection being scored
                 require confirmed-standing posture (same bent-knee check as
                 (2)) — box height is only a real-height proxy while
                 standing, and real footage the same day showed a seated
                 adult read as confident CHILD when this wasn't enforced.
                 See _relative_height_score.
  4. appearance — does the crop match the student uniform (white top,
                 black bottom)? Scale-independent, unlike (2)'s keypoint
                 ratios — added 2026-09-08 after real footage showed (2)
                 misreading small/distant children as confident adults
                 (ear-keypoint noise dominates at small pixel scale). Only
                 ever pulls toward CHILD (see _uniform_score for why).
  5. confidence — the detector's own confidence is used as a *reliability
                 weight* (how much this frame's contribution should count in
                 the rolling history), not as a direction signal, since
                 detection confidence says nothing about age.

Each signal contributes only when it can produce one confidently — this
frame's fused score is the weight-average of whichever ones fired, not a
fixed formula assuming all are present. With nothing available at all, the
result stays neutral 0.5/UNKNOWN, which is correct and honest rather than a
guess.
"""
from __future__ import annotations

import logging
import math
from collections import deque

import cv2
import numpy as np

from app.cv.calibration.roi import CameraCalibration
from app.cv.classifier.base import AgeGroupClassifier, FrameClassification
from app.cv.detector.base import Detection
from app.cv.pose.base import PoseResult

logger = logging.getLogger(__name__)

GEOMETRY_WEIGHT = 0.35
POSE_WEIGHT = 0.30
RELATIVE_HEIGHT_WEIGHT = 0.25
APPEARANCE_WEIGHT = 0.10

# Relative-height signal: compares each detection's own pixel height against
# a rolling reference for THIS camera, instead of requiring the ROI/
# calibration admin step (which may never get done — geometry above then
# contributes nothing). Since this classroom's children are a known, narrow
# band (3-3.5y, 94-99cm), a robust LOW percentile of recent detection
# heights should closely track "94-99cm in pixels right now" as long as
# children are the majority of what the camera sees — which then makes any
# detection notably taller (the known real ratio for a ~155-175cm adult
# against that band is ~1.57-1.86x) a strong, calibration-free ADULT signal.
# Added 2026-09-08 specifically so a genuinely tall adult gets pulled toward
# ADULT even on frames where pose/appearance are ambiguous or unavailable.
HEIGHT_REFERENCE_WINDOW = 150  # per camera_id — see _relative_height_score
HEIGHT_REFERENCE_MIN_SAMPLES = 10  # don't trust a reference built from too few detections yet
HEIGHT_REFERENCE_PERCENTILE = 30  # low percentile: robust to an adult occasionally inflating the mix
ADULT_HEIGHT_RATIO_MIN = 1.4  # sigmoid midpoint: matches the real ~1.4x+ adult/child ratio
HEIGHT_RATIO_STEEPNESS = 6.0

# Minimum ear-to-ear width (pixels) before the shoulder/head ratio is
# trusted. The actual noise-sensitive quantity is head_width, not
# shoulder_width — ears sit much closer together than shoulders, so the same
# few pixels of keypoint localization error is a much bigger relative error
# on head_width. An earlier version of this guard used shoulder_width
# instead (48px), which real footage on 2026-09-08 showed breaks the moment
# the camera frames a wider/busier scene: real adults' shoulder_width
# shrinks right along with everyone else's in a wider shot and got excluded
# just as often as the noisy small children the guard was meant to catch.
# Gating on head_width's own absolute size targets the actual noise source
# instead of a proxy that scales with camera framing.
MIN_HEAD_WIDTH_FOR_BUILD_RATIO = 12.0

# How far the ear-midpoint may drift from the shoulder-midpoint (as a
# fraction of head_width) before a turned/profile head is suspected and the
# ratio is rejected. Real footage 2026-09-08: a child with a turned head
# read as confident ADULT (foreshortened ear separation, normal shoulder
# width) — this rejects that measurement instead of trusting it blindly.
HEAD_TURN_OFFSET_RATIO = 0.5

# Welmont Lalkothi's student uniform (per the site): white top, black
# shorts/bottoms — confirmed 2026-09-08. A confident match is strong,
# scale-independent evidence of a student, immune to the pose-keypoint
# noise above. Deliberately one-directional: a confident match pulls the
# score toward CHILD, but a non-match does NOT push toward ADULT (adults'
# clothing varies far more than "not this specific uniform").
UNIFORM_TOP_V_MIN = 150.0  # brightness floor for "white" (0-255 V channel)
UNIFORM_TOP_S_MAX = 60.0  # saturation ceiling for "white" (0-255 S channel)
UNIFORM_BOTTOM_V_MAX = 70.0  # brightness ceiling for "black" (0-255 V channel)
UNIFORM_MATCH_SCORE = 0.15  # adult-likeness contributed by a confident match


def _sigmoid(x: float, midpoint: float, steepness: float) -> float:
    return 1.0 / (1.0 + math.exp(-steepness * (x - midpoint)))


class HeuristicAgeClassifier(AgeGroupClassifier):
    def __init__(self) -> None:
        # Keyed by calibration.camera_id — this classifier instance is
        # shared across every camera worker ("shared CV models" in
        # app.main), so the rolling height reference must be scoped per
        # camera itself, not mixed together across different cameras'
        # distances/scales.
        self._height_refs: dict[str, deque[float]] = {}

    def classify(
        self,
        frame: np.ndarray,
        detection: Detection,
        pose: PoseResult | None,
        calibration: CameraCalibration,
    ) -> FrameClassification:
        signals: dict[str, float] = {}

        weighted = [
            (GEOMETRY_WEIGHT, self._geometry_score(detection, calibration), "geometry"),
            (POSE_WEIGHT, self._pose_score(pose, detection), "pose"),
            (RELATIVE_HEIGHT_WEIGHT, self._relative_height_score(detection, calibration, pose), "relative_height"),
            (APPEARANCE_WEIGHT, self._uniform_score(frame, detection, pose), "appearance"),
        ]
        available = [(w, s) for w, s, _ in weighted if s is not None]
        for _, s, name in weighted:
            if s is not None:
                signals[name] = s

        if available:
            total_weight = sum(w for w, _ in available)
            fused = sum(w * s for w, s in available) / total_weight
        else:
            fused = 0.5  # no usable signal this frame — stay neutral, let temporal window decide

        signals["confidence_weight"] = detection.confidence
        signals["fused"] = fused
        return FrameClassification(adult_score=fused, signals=signals)

    def _relative_height_score(
        self, detection: Detection, calibration: CameraCalibration, pose: PoseResult | None
    ) -> float | None:
        """Compares this detection's own pixel height against a rolling,
        calibration-free reference for this specific camera — see the
        constants above for why a low percentile of recent heights tracks
        the known 94-99cm child band, and why that makes a notably taller
        detection strong evidence of an adult regardless of what pose or
        appearance say this frame.

        Only ever compares standing-to-standing. Bounding-box height is a
        real-height proxy ONLY while standing — a seated person's box spans
        torso+head, not full body, so a seated adult can produce a shorter
        box than a standing child despite being taller. Confirmed on real
        footage 2026-09-08: a seated adult was read as confident CHILD by
        this signal precisely because her seated height was compared against
        a reference contaminated with standing children's heights. Both the
        reference itself and the detection being scored now require
        confirmed-standing posture (via the same bent-knee check used for
        the leg-ratio pose signal) — unknown or bent-knee posture abstains
        rather than guessing.
        """
        if not self._is_confirmed_standing(pose):
            return None

        heights = self._height_refs.setdefault(calibration.camera_id, deque(maxlen=HEIGHT_REFERENCE_WINDOW))
        heights.append(detection.height)

        if len(heights) < HEIGHT_REFERENCE_MIN_SAMPLES:
            return None  # reference not warmed up yet for this camera

        reference = float(np.percentile(heights, HEIGHT_REFERENCE_PERCENTILE))
        if reference <= 1e-3:
            return None

        ratio = detection.height / reference
        return _sigmoid(ratio, ADULT_HEIGHT_RATIO_MIN, HEIGHT_RATIO_STEEPNESS)

    @staticmethod
    def _is_confirmed_standing(pose: PoseResult | None) -> bool:
        if pose is None:
            return False
        hip = _midpoint(pose.get("left_hip"), pose.get("right_hip"))
        ankle = _midpoint(pose.get("left_ankle"), pose.get("right_ankle"))
        knee = _midpoint(pose.get("left_knee"), pose.get("right_knee"))
        if not hip or not ankle:
            return False  # can't verify posture — don't guess
        return _leg_is_extended(hip, knee, ankle)

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

    def _uniform_score(self, frame: np.ndarray, detection: Detection, pose: PoseResult | None) -> float | None:
        """Confidently matching the student uniform (white top, black
        bottom) is strong, scale-independent evidence of a child — added
        2026-09-08 after real footage showed the pose-based ratio reading
        confident-but-wrong ADULT for small/distant children. Deliberately
        one-directional: only ever pulls toward CHILD, never toward ADULT,
        since "not wearing this specific uniform" is much weaker evidence
        (a visitor, or a staff member in different colors) than "wearing
        it" is for a student.
        """
        if frame is None or frame.size == 0:
            return None

        h, w = frame.shape[:2]
        x1, y1 = max(0, int(detection.x1)), max(0, int(detection.y1))
        x2, y2 = min(w, int(detection.x2)), min(h, int(detection.y2))
        box_w, box_h = x2 - x1, y2 - y1
        if box_w < 8 or box_h < 20:
            return None  # too small to sample color reliably

        margin_x = max(1, int(box_w * 0.15))
        left, right = x1 + margin_x, x2 - margin_x
        if right <= left:
            left, right = x1, x2

        (top_y1, top_y2), (bottom_y1, bottom_y2) = self._uniform_crop_bands(pose, y1, y2, box_h)
        top_crop = frame[top_y1:top_y2, left:right]
        bottom_crop = frame[bottom_y1:bottom_y2, left:right]
        if top_crop.size == 0 or bottom_crop.size == 0:
            return None

        top_hsv = cv2.cvtColor(top_crop, cv2.COLOR_BGR2HSV)
        bottom_hsv = cv2.cvtColor(bottom_crop, cv2.COLOR_BGR2HSV)
        top_v, top_s = float(top_hsv[..., 2].mean()), float(top_hsv[..., 1].mean())
        bottom_v = float(bottom_hsv[..., 2].mean())

        top_is_white = top_v >= UNIFORM_TOP_V_MIN and top_s <= UNIFORM_TOP_S_MAX
        bottom_is_black = bottom_v <= UNIFORM_BOTTOM_V_MAX

        logger.debug(
            "UNIFORM_DEBUG top_v=%.0f top_s=%.0f bottom_v=%.0f top_white=%s bottom_black=%s",
            top_v, top_s, bottom_v, top_is_white, bottom_is_black,
        )

        if top_is_white and bottom_is_black:
            return UNIFORM_MATCH_SCORE
        return None

    @staticmethod
    def _uniform_crop_bands(
        pose: PoseResult | None, y1: int, y2: int, box_h: int
    ) -> tuple[tuple[int, int], tuple[int, int]]:
        """Where to sample "top" (shirt) and "bottom" (shorts) color from,
        vertically. Prefers real shoulder/hip/ankle keypoints when
        available — real footage on 2026-09-08 showed the previous fixed-
        fraction bands (15-45% / 55-85% of box height) sampling a child's
        *hair*, not their shirt: a child's head takes up a far bigger share
        of their box height than an adult's (the same proportional-head-size
        fact behind the pose signal above), so a fixed fraction tuned
        loosely for an adult-shaped body lands in the wrong place on a
        child. Falls back to the fixed fraction only when shoulder/hip/ankle
        aren't confidently visible this frame.
        """
        if pose is not None:
            shoulder = _midpoint(pose.get("left_shoulder"), pose.get("right_shoulder"))
            hip = _midpoint(pose.get("left_hip"), pose.get("right_hip"))
            ankle = _midpoint(pose.get("left_ankle"), pose.get("right_ankle"))
            if shoulder and hip and ankle and hip[1] > shoulder[1] + 4 and ankle[1] > hip[1] + 4:
                top = (max(y1, int(shoulder[1])), min(y2, int(hip[1])))
                bottom = (max(y1, int(hip[1])), min(y2, int(ankle[1])))
                if top[1] > top[0] and bottom[1] > bottom[0]:
                    return top, bottom

        return (
            (y1 + int(box_h * 0.15), y1 + int(box_h * 0.45)),
            (y1 + int(box_h * 0.55), y1 + int(box_h * 0.85)),
        )

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
        head_turned = None
        if left_ear and right_ear:
            head_width = _dist(left_ear, right_ear)
            if shoulder_width > 1e-3 and head_width >= MIN_HEAD_WIDTH_FOR_BUILD_RATIO:
                # A turned/profile head foreshortens ear-to-ear distance in
                # 2D without changing shoulder width — real footage
                # 2026-09-08 showed this read a child as confident ADULT.
                # A frontal or direct-rear view keeps the ear-midpoint
                # aligned with the shoulder-midpoint on the horizontal axis;
                # a turned head visibly offsets it (the near ear dominates
                # the average). Reject the ratio when that offset is large
                # relative to the measured head width itself.
                ear_mid_x = (left_ear[0] + right_ear[0]) / 2.0
                head_turned = abs(ear_mid_x - shoulder[0]) > head_width * HEAD_TURN_OFFSET_RATIO
                if not head_turned:
                    # Shoulder-width-to-head-width: a 3-3.5y toddler's head
                    # is nearly as wide as their shoulders; an adult's
                    # shoulders are far broader than their head. Holds
                    # whether the person is standing, sitting on the floor,
                    # or bent over a desk, and facing the camera or away
                    # from it.
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
            "POSE_DEBUG shoulder_w=%.1f ears=%s head_turned=%s build_ratio=%s hip=%s ankle=%s leg_extended=%s "
            "leg_ratio=%s(unscored) scores=%s",
            shoulder_width,
            bool(left_ear and right_ear),
            head_turned,
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
