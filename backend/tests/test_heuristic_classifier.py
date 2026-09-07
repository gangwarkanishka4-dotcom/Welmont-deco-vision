"""Validates the fallback classifier's signal fusion (spec §2: multiple
signals, not just bbox height) degrades gracefully as signals become
unavailable, and that each signal actually points the right direction.

The pose sub-signals were tuned against real footage from the Welmont
Lalkothi cameras on 2026-09-07 (see heuristic_classifier.py's POSE_DEBUG
log). That footage showed the ear-to-ear head-width ratio to be reliable and
consistent for real people, but the leg-length ratio and the box-top head
proxy both produced wrong-direction results on this camera's lens/mounting
angle — so only the ear-based ratio is currently scored. Fixtures below
reflect that: poses meant to demonstrate a working pose signal include ear
keypoints; poses testing the now-disabled paths (legs, box-top) verify they
no longer affect the outcome.
"""
from __future__ import annotations

import numpy as np

from app.cv.calibration.roi import CameraCalibration, ReferencePoint
from app.cv.classifier.heuristic_classifier import HeuristicAgeClassifier
from app.cv.detector.base import Detection
from app.cv.pose.base import PoseResult

FRAME = np.zeros((480, 640, 3), dtype=np.uint8)
CLASSIFIER = HeuristicAgeClassifier()


def _calibration(with_reference_points: bool) -> CameraCalibration:
    points = [ReferencePoint(200, 100), ReferencePoint(600, 300)] if with_reference_points else []
    return CameraCalibration(camera_id="cam-1", reference_points=points)


def _adult_like_pose() -> PoseResult:
    # Shoulders far broader than ear-to-ear head width — adult-typical build.
    return PoseResult(
        keypoints={
            "left_ear": (-4, 5, 1.0),
            "right_ear": (4, 5, 1.0),
            "left_shoulder": (-25, 20, 1.0),
            "right_shoulder": (25, 20, 1.0),
            "left_hip": (-10, 60, 1.0),
            "right_hip": (10, 60, 1.0),
            "left_ankle": (-10, 160, 1.0),
            "right_ankle": (10, 160, 1.0),
        }
    )


def _child_like_pose() -> PoseResult:
    # Head nearly as wide as the shoulders — toddler-typical build.
    return PoseResult(
        keypoints={
            "left_ear": (-9, 5, 1.0),
            "right_ear": (9, 5, 1.0),
            "left_shoulder": (-10, 30, 1.0),
            "right_shoulder": (10, 30, 1.0),
            "left_hip": (-10, 90, 1.0),
            "right_hip": (10, 90, 1.0),
            "left_ankle": (-10, 110, 1.0),
            "right_ankle": (10, 110, 1.0),
        }
    )


def test_no_signals_available_returns_neutral_score():
    calibration = _calibration(with_reference_points=False)
    detection = Detection(x1=0, y1=0, x2=50, y2=100, confidence=0.9)
    result = CLASSIFIER.classify(FRAME, detection, pose=None, calibration=calibration)
    assert result.adult_score == 0.5
    assert "geometry" not in result.signals
    assert "pose" not in result.signals


def test_geometry_only_ratio_above_adult_threshold_leans_adult():
    calibration = _calibration(with_reference_points=True)
    calibration.adult_height_ratio = 0.85
    calibration.child_height_ratio = 0.60
    # foot at y=600 -> expected_adult_height_px = 300; height=280 -> ratio=280/300≈0.93 (> adult threshold)
    detection = Detection(x1=0, y1=320, x2=50, y2=600, confidence=0.9)
    result = CLASSIFIER.classify(FRAME, detection, pose=None, calibration=calibration)
    assert result.adult_score > 0.5
    assert "pose" not in result.signals


def test_geometry_only_ratio_below_child_threshold_leans_child():
    calibration = _calibration(with_reference_points=True)
    calibration.adult_height_ratio = 0.85
    calibration.child_height_ratio = 0.60
    # foot at y=600 -> expected=300; height=120 -> ratio=0.4 (< child threshold)
    detection = Detection(x1=0, y1=480, x2=50, y2=600, confidence=0.9)
    result = CLASSIFIER.classify(FRAME, detection, pose=None, calibration=calibration)
    assert result.adult_score < 0.5


def test_pose_only_when_uncalibrated_adult_proportions_lean_adult():
    calibration = _calibration(with_reference_points=False)
    detection = Detection(x1=0, y1=0, x2=50, y2=160, confidence=0.9)
    result = CLASSIFIER.classify(FRAME, detection, pose=_adult_like_pose(), calibration=calibration)
    assert "geometry" not in result.signals
    assert result.adult_score > 0.5


def test_pose_only_when_uncalibrated_child_proportions_lean_child():
    calibration = _calibration(with_reference_points=False)
    detection = Detection(x1=0, y1=0, x2=50, y2=110, confidence=0.9)
    result = CLASSIFIER.classify(FRAME, detection, pose=_child_like_pose(), calibration=calibration)
    assert result.adult_score < 0.5


def test_geometry_and_pose_agreeing_reinforce_each_other():
    calibration = _calibration(with_reference_points=True)
    detection = Detection(x1=0, y1=320, x2=50, y2=600, confidence=0.9)  # adult-like geometry
    geometry_only = CLASSIFIER.classify(FRAME, detection, pose=None, calibration=calibration)
    both = CLASSIFIER.classify(FRAME, detection, pose=_adult_like_pose(), calibration=calibration)
    assert both.adult_score > 0.5
    assert "pose" in both.signals and "geometry" in both.signals


def test_incomplete_pose_keypoints_falls_back_to_geometry_only():
    calibration = _calibration(with_reference_points=True)
    detection = Detection(x1=0, y1=320, x2=50, y2=600, confidence=0.9)
    partial_pose = PoseResult(keypoints={"nose": (0, 0, 1.0)})  # missing hips/ankles/shoulders
    result = CLASSIFIER.classify(FRAME, detection, pose=partial_pose, calibration=calibration)
    assert "pose" not in result.signals
    assert "geometry" in result.signals


def test_pose_score_available_without_face_visible():
    # A preschooler facing away from the camera: shoulders/hips/ankles/ears
    # visible, no nose/eyes at all. The pose signal must not silently
    # disappear just because the child isn't facing the camera — ears
    # (visible from behind) are what carries it, not a frontal face.
    calibration = _calibration(with_reference_points=False)
    detection = Detection(x1=0, y1=0, x2=50, y2=110, confidence=0.9)
    faceless_child_pose = PoseResult(
        keypoints={
            "left_ear": (-9, 5, 1.0),
            "right_ear": (9, 5, 1.0),
            "left_shoulder": (-10, 30, 1.0),
            "right_shoulder": (10, 30, 1.0),
            "left_hip": (-10, 90, 1.0),
            "right_hip": (10, 90, 1.0),
            "left_ankle": (-10, 110, 1.0),
            "right_ankle": (10, 110, 1.0),
        }
    )
    result = CLASSIFIER.classify(FRAME, detection, pose=faceless_child_pose, calibration=calibration)
    assert "pose" in result.signals
    assert result.adult_score < 0.5


def test_back_of_head_adult_uses_ear_width_not_face():
    # An adult seen from behind: no face keypoints at all, but ears are
    # visible (COCO keypoints estimate ear position even from behind). Wide
    # shoulders relative to a narrow ear-to-ear head width must still read
    # as adult, with no leg data needed at all.
    calibration = _calibration(with_reference_points=False)
    detection = Detection(x1=0, y1=0, x2=80, y2=60, confidence=0.9)
    back_of_head_adult_pose = PoseResult(
        keypoints={
            "left_ear": (-7, 12, 1.0),
            "right_ear": (7, 12, 1.0),
            "left_shoulder": (-25, 25, 1.0),
            "right_shoulder": (25, 25, 1.0),
        }
    )
    result = CLASSIFIER.classify(FRAME, detection, pose=back_of_head_adult_pose, calibration=calibration)
    assert "pose" in result.signals
    assert result.adult_score > 0.5


def test_back_of_head_child_uses_ear_width_not_face():
    # A toddler seen from behind: head nearly as wide as their narrow
    # shoulders — the opposite proportions from the adult case above.
    calibration = _calibration(with_reference_points=False)
    detection = Detection(x1=0, y1=0, x2=40, y2=40, confidence=0.9)
    back_of_head_child_pose = PoseResult(
        keypoints={
            "left_ear": (-9, 10, 1.0),
            "right_ear": (9, 10, 1.0),
            "left_shoulder": (-11, 22, 1.0),
            "right_shoulder": (11, 22, 1.0),
        }
    )
    result = CLASSIFIER.classify(FRAME, detection, pose=back_of_head_child_pose, calibration=calibration)
    assert "pose" in result.signals
    assert result.adult_score < 0.5


def test_sitting_adult_still_reads_adult_via_ears_despite_bent_legs():
    # Broad shoulders, narrow ear-to-ear head width (adult-like), but sitting
    # cross-legged so hip->ankle is short via a sharply bent knee. The
    # (unscored) leg ratio would misread this as child-like on its own — the
    # ear-based signal must carry the score regardless.
    calibration = _calibration(with_reference_points=False)
    detection = Detection(x1=0, y1=0, x2=80, y2=80, confidence=0.9)
    sitting_adult_pose = PoseResult(
        keypoints={
            "left_ear": (-7, 8, 1.0),
            "right_ear": (7, 8, 1.0),
            "left_shoulder": (-25, 20, 1.0),
            "right_shoulder": (25, 20, 1.0),
            "left_hip": (-15, 60, 1.0),
            "right_hip": (15, 60, 1.0),
            "left_knee": (-30, 75, 1.0),
            "right_knee": (30, 75, 1.0),
            "left_ankle": (-15, 65, 1.0),
            "right_ankle": (15, 65, 1.0),
        }
    )
    result = CLASSIFIER.classify(FRAME, detection, pose=sitting_adult_pose, calibration=calibration)
    assert result.adult_score > 0.5


def test_leg_ratio_alone_does_not_drive_classification():
    # Real-footage evidence (2026-09-07) showed the leg-length ratio reading
    # wrong-direction on this camera even for a confidently-extended leg —
    # it must no longer be able to produce a pose score on its own, with no
    # ears present to corroborate it either way.
    calibration = _calibration(with_reference_points=False)
    detection = Detection(x1=0, y1=0, x2=50, y2=160, confidence=0.9)
    straight_leg_no_ears = PoseResult(
        keypoints={
            "left_shoulder": (-10, 20, 1.0),
            "right_shoulder": (10, 20, 1.0),
            "left_hip": (-10, 60, 1.0),
            "right_hip": (10, 60, 1.0),
            "left_knee": (-10, 110, 1.0),
            "right_knee": (10, 110, 1.0),
            "left_ankle": (-10, 160, 1.0),
            "right_ankle": (10, 160, 1.0),
        }
    )
    result = CLASSIFIER.classify(FRAME, detection, pose=straight_leg_no_ears, calibration=calibration)
    assert "pose" not in result.signals
    assert result.adult_score == 0.5


def test_pose_score_requires_ears_not_box_top_head_proxy():
    # The box-top-to-shoulder-line head-length proxy was found unreliable on
    # real footage (produced wildly different numbers than the ear-based
    # measurement for comparable people) and must no longer independently
    # produce a pose score — with no ears present, varying the detection
    # box's top edge must not change the outcome (there is none).
    calibration = _calibration(with_reference_points=False)
    keypoints = {
        "left_shoulder": (-10, 20, 1.0),
        "right_shoulder": (10, 20, 1.0),
        "left_hip": (-10, 60, 1.0),
        "right_hip": (10, 60, 1.0),
        "left_ankle": (-10, 160, 1.0),
        "right_ankle": (10, 160, 1.0),
    }
    no_ears_pose = PoseResult(keypoints=keypoints)

    result_a = CLASSIFIER.classify(FRAME, Detection(x1=0, y1=0, x2=50, y2=160, confidence=0.9), pose=no_ears_pose, calibration=calibration)
    result_b = CLASSIFIER.classify(FRAME, Detection(x1=0, y1=-50, x2=50, y2=160, confidence=0.9), pose=no_ears_pose, calibration=calibration)
    assert "pose" not in result_a.signals
    assert "pose" not in result_b.signals
