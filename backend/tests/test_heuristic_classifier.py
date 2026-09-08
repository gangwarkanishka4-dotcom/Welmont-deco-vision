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
from app.cv.classifier.heuristic_classifier import UNIFORM_MATCH_SCORE, HeuristicAgeClassifier
from app.cv.detector.base import Detection
from app.cv.pose.base import PoseResult

FRAME = np.zeros((480, 640, 3), dtype=np.uint8)


def _calibration(with_reference_points: bool) -> CameraCalibration:
    points = [ReferencePoint(200, 100), ReferencePoint(600, 300)] if with_reference_points else []
    return CameraCalibration(camera_id="cam-1", reference_points=points)


def _adult_like_pose() -> PoseResult:
    # Shoulders far broader than ear-to-ear head width — adult-typical build.
    # Head width (14) kept above MIN_HEAD_WIDTH_FOR_BUILD_RATIO (12).
    return PoseResult(
        keypoints={
            "left_ear": (-7, 5, 1.0),
            "right_ear": (7, 5, 1.0),
            "left_shoulder": (-25, 20, 1.0),
            "right_shoulder": (25, 20, 1.0),
            "left_hip": (-10, 60, 1.0),
            "right_hip": (10, 60, 1.0),
            "left_ankle": (-10, 160, 1.0),
            "right_ankle": (10, 160, 1.0),
        }
    )


def _child_like_pose() -> PoseResult:
    # Head nearly as wide as the shoulders — toddler-typical build. Shoulder
    # width kept >= MIN_SHOULDER_WIDTH_FOR_BUILD_RATIO (48px) so the ratio
    # isn't excluded by the small-detection noise guard.
    return PoseResult(
        keypoints={
            "left_ear": (-24, 5, 1.0),
            "right_ear": (24, 5, 1.0),
            "left_shoulder": (-27, 30, 1.0),
            "right_shoulder": (27, 30, 1.0),
            "left_hip": (-10, 90, 1.0),
            "right_hip": (10, 90, 1.0),
            "left_ankle": (-10, 110, 1.0),
            "right_ankle": (10, 110, 1.0),
        }
    )


def test_no_signals_available_returns_neutral_score():
    calibration = _calibration(with_reference_points=False)
    detection = Detection(x1=0, y1=0, x2=50, y2=100, confidence=0.9)
    result = HeuristicAgeClassifier().classify(FRAME, detection, pose=None, calibration=calibration)
    assert result.adult_score == 0.5
    assert "geometry" not in result.signals
    assert "pose" not in result.signals


def test_geometry_only_ratio_above_adult_threshold_leans_adult():
    calibration = _calibration(with_reference_points=True)
    calibration.adult_height_ratio = 0.85
    calibration.child_height_ratio = 0.60
    # foot at y=600 -> expected_adult_height_px = 300; height=280 -> ratio=280/300≈0.93 (> adult threshold)
    detection = Detection(x1=0, y1=320, x2=50, y2=600, confidence=0.9)
    result = HeuristicAgeClassifier().classify(FRAME, detection, pose=None, calibration=calibration)
    assert result.adult_score > 0.5
    assert "pose" not in result.signals


def test_geometry_only_ratio_below_child_threshold_leans_child():
    calibration = _calibration(with_reference_points=True)
    calibration.adult_height_ratio = 0.85
    calibration.child_height_ratio = 0.60
    # foot at y=600 -> expected=300; height=120 -> ratio=0.4 (< child threshold)
    detection = Detection(x1=0, y1=480, x2=50, y2=600, confidence=0.9)
    result = HeuristicAgeClassifier().classify(FRAME, detection, pose=None, calibration=calibration)
    assert result.adult_score < 0.5


def test_pose_only_when_uncalibrated_adult_proportions_lean_adult():
    calibration = _calibration(with_reference_points=False)
    detection = Detection(x1=0, y1=0, x2=50, y2=160, confidence=0.9)
    result = HeuristicAgeClassifier().classify(FRAME, detection, pose=_adult_like_pose(), calibration=calibration)
    assert "geometry" not in result.signals
    assert result.adult_score > 0.5


def test_pose_only_when_uncalibrated_child_proportions_lean_child():
    calibration = _calibration(with_reference_points=False)
    detection = Detection(x1=0, y1=0, x2=50, y2=110, confidence=0.9)
    result = HeuristicAgeClassifier().classify(FRAME, detection, pose=_child_like_pose(), calibration=calibration)
    assert result.adult_score < 0.5


def test_geometry_and_pose_agreeing_reinforce_each_other():
    calibration = _calibration(with_reference_points=True)
    detection = Detection(x1=0, y1=320, x2=50, y2=600, confidence=0.9)  # adult-like geometry
    geometry_only = HeuristicAgeClassifier().classify(FRAME, detection, pose=None, calibration=calibration)
    both = HeuristicAgeClassifier().classify(FRAME, detection, pose=_adult_like_pose(), calibration=calibration)
    assert both.adult_score > 0.5
    assert "pose" in both.signals and "geometry" in both.signals


def test_incomplete_pose_keypoints_falls_back_to_geometry_only():
    calibration = _calibration(with_reference_points=True)
    detection = Detection(x1=0, y1=320, x2=50, y2=600, confidence=0.9)
    partial_pose = PoseResult(keypoints={"nose": (0, 0, 1.0)})  # missing hips/ankles/shoulders
    result = HeuristicAgeClassifier().classify(FRAME, detection, pose=partial_pose, calibration=calibration)
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
            "left_ear": (-24, 5, 1.0),
            "right_ear": (24, 5, 1.0),
            "left_shoulder": (-27, 30, 1.0),
            "right_shoulder": (27, 30, 1.0),
            "left_hip": (-10, 90, 1.0),
            "right_hip": (10, 90, 1.0),
            "left_ankle": (-10, 110, 1.0),
            "right_ankle": (10, 110, 1.0),
        }
    )
    result = HeuristicAgeClassifier().classify(FRAME, detection, pose=faceless_child_pose, calibration=calibration)
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
    result = HeuristicAgeClassifier().classify(FRAME, detection, pose=back_of_head_adult_pose, calibration=calibration)
    assert "pose" in result.signals
    assert result.adult_score > 0.5


def test_back_of_head_child_uses_ear_width_not_face():
    # A toddler seen from behind: head nearly as wide as their narrow
    # shoulders — the opposite proportions from the adult case above.
    calibration = _calibration(with_reference_points=False)
    detection = Detection(x1=0, y1=0, x2=80, y2=80, confidence=0.9)
    back_of_head_child_pose = PoseResult(
        keypoints={
            "left_ear": (-24, 10, 1.0),
            "right_ear": (24, 10, 1.0),
            "left_shoulder": (-27, 22, 1.0),
            "right_shoulder": (27, 22, 1.0),
        }
    )
    result = HeuristicAgeClassifier().classify(FRAME, detection, pose=back_of_head_child_pose, calibration=calibration)
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
    result = HeuristicAgeClassifier().classify(FRAME, detection, pose=sitting_adult_pose, calibration=calibration)
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
    result = HeuristicAgeClassifier().classify(FRAME, detection, pose=straight_leg_no_ears, calibration=calibration)
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

    result_a = HeuristicAgeClassifier().classify(FRAME, Detection(x1=0, y1=0, x2=50, y2=160, confidence=0.9), pose=no_ears_pose, calibration=calibration)
    result_b = HeuristicAgeClassifier().classify(FRAME, Detection(x1=0, y1=-50, x2=50, y2=160, confidence=0.9), pose=no_ears_pose, calibration=calibration)
    assert "pose" not in result_a.signals
    assert "pose" not in result_b.signals


def test_small_head_width_excludes_unreliable_ear_ratio():
    # The noise-sensitive quantity is head_width (ear-to-ear), not
    # shoulder_width — ears sit much closer together, so the same few
    # pixels of keypoint error is a much bigger relative error on head_width.
    # A tiny head_width must be excluded regardless of how confident the
    # shoulder measurement looks.
    calibration = _calibration(with_reference_points=False)
    detection = Detection(x1=0, y1=0, x2=50, y2=50, confidence=0.9)
    tiny_head_width_pose = PoseResult(
        keypoints={
            "left_ear": (-4, 5, 1.0),
            "right_ear": (4, 5, 1.0),  # head width 8 — below the 12px noise floor
            "left_shoulder": (-25, 20, 1.0),
            "right_shoulder": (25, 20, 1.0),  # shoulder width 50 — plenty large, but irrelevant to the guard
        }
    )
    result = HeuristicAgeClassifier().classify(FRAME, detection, pose=tiny_head_width_pose, calibration=calibration)
    assert "pose" not in result.signals
    assert result.adult_score == 0.5


def test_small_shoulder_width_no_longer_blocks_ratio_with_adequate_head_width():
    # Real footage (2026-09-08): a wider/busier camera framing shrinks
    # everyone's shoulder_width, including real adults' — an earlier version
    # of this guard gated on shoulder_width (48px) and excluded real adults
    # in exactly this situation. Gating on head_width instead must let a
    # confidently adult-shaped ratio through even when shoulder_width itself
    # is modest, as long as head_width is large enough to trust.
    calibration = _calibration(with_reference_points=False)
    detection = Detection(x1=0, y1=0, x2=50, y2=50, confidence=0.9)
    smaller_scale_adult_pose = PoseResult(
        keypoints={
            "left_ear": (-9, 5, 1.0),
            "right_ear": (9, 5, 1.0),  # head width 18 — comfortably above the 12px floor
            "left_shoulder": (-15, 20, 1.0),
            "right_shoulder": (15, 20, 1.0),  # shoulder width 30 — would have failed the old 48px guard
        }
    )
    result = HeuristicAgeClassifier().classify(FRAME, detection, pose=smaller_scale_adult_pose, calibration=calibration)
    assert "pose" in result.signals
    assert result.adult_score > 0.5


def test_uniform_match_pulls_score_toward_child():
    # White top + black bottom (Welmont's student uniform) is scale-
    # independent evidence of a child, confirmed 2026-09-08. No pose or
    # geometry signal here — appearance alone must carry the score.
    calibration = _calibration(with_reference_points=False)
    detection = Detection(x1=10, y1=0, x2=90, y2=100, confidence=0.9)
    frame = np.zeros((100, 100, 3), dtype=np.uint8)
    frame[10:50, :] = 255  # white top band (bottom band stays black)

    result = HeuristicAgeClassifier().classify(frame, detection, pose=None, calibration=calibration)
    assert "appearance" in result.signals
    assert result.adult_score < 0.5


def test_non_matching_clothing_does_not_signal_adult():
    # Not wearing the uniform is NOT evidence of being an adult (a visitor,
    # or staff in different colors) — appearance must abstain (None), never
    # push the score up.
    calibration = _calibration(with_reference_points=False)
    detection = Detection(x1=10, y1=0, x2=90, y2=100, confidence=0.9)
    frame = np.zeros((100, 100, 3), dtype=np.uint8)
    frame[10:50, :] = (0, 0, 255)  # saturated red top band — not white

    result = HeuristicAgeClassifier().classify(frame, detection, pose=None, calibration=calibration)
    assert "appearance" not in result.signals
    assert result.adult_score == 0.5


def _child_sized_detection(height: float) -> Detection:
    return Detection(x1=0, y1=0, x2=50, y2=height, confidence=0.9)


def _standing_pose() -> PoseResult:
    # Only hip/ankle (no knee) needed to confirm standing — _leg_is_extended
    # gives the benefit of the doubt when the knee isn't visible.
    return PoseResult(keypoints={"left_hip": (-10, 40, 1.0), "right_hip": (10, 40, 1.0),
                                  "left_ankle": (-10, 100, 1.0), "right_ankle": (10, 100, 1.0)})


def _sitting_pose() -> PoseResult:
    # A sharply bent knee — the same bent-knee shape used in the sitting-
    # adult pose test above.
    return PoseResult(keypoints={"left_hip": (-15, 40, 1.0), "right_hip": (15, 40, 1.0),
                                  "left_knee": (-30, 55, 1.0), "right_knee": (30, 55, 1.0),
                                  "left_ankle": (-15, 45, 1.0), "right_ankle": (15, 45, 1.0)})


def test_relative_height_absent_until_reference_warmed_up():
    # No calibration, no matching uniform — only the relative-height signal
    # could possibly fire, and it must not until it has seen enough
    # confirmed-standing detections for this camera to build a reference.
    calibration = _calibration(with_reference_points=False)
    classifier = HeuristicAgeClassifier()
    frame = np.zeros((10, 10, 3), dtype=np.uint8)  # too small for appearance to ever match

    for _ in range(9):  # one short of HEIGHT_REFERENCE_MIN_SAMPLES (10)
        result = classifier.classify(frame, _child_sized_detection(100), pose=_standing_pose(), calibration=calibration)
    assert "relative_height" not in result.signals
    assert result.adult_score == 0.5


def test_relative_height_flags_a_notably_taller_detection_as_adult():
    # Feed the same camera many child-sized (~100px) standing detections to
    # warm up its rolling reference, then a standing detection ~1.7x taller
    # (matching the real adult/94-99cm-band ratio) must read as
    # adult-leaning from this signal alone.
    calibration = _calibration(with_reference_points=False)
    classifier = HeuristicAgeClassifier()
    frame = np.zeros((10, 10, 3), dtype=np.uint8)

    for _ in range(20):
        classifier.classify(frame, _child_sized_detection(100), pose=_standing_pose(), calibration=calibration)

    result = classifier.classify(frame, _child_sized_detection(170), pose=_standing_pose(), calibration=calibration)
    assert "relative_height" in result.signals
    assert result.adult_score > 0.5


def test_relative_height_reference_is_scoped_per_camera():
    # This classifier instance is shared across every camera worker in
    # production — a rolling reference warmed up on one camera must not
    # leak into a completely different camera's detections.
    classifier = HeuristicAgeClassifier()
    frame = np.zeros((10, 10, 3), dtype=np.uint8)
    cam_a = CameraCalibration(camera_id="cam-a", reference_points=[])
    cam_b = CameraCalibration(camera_id="cam-b", reference_points=[])

    for _ in range(20):
        classifier.classify(frame, _child_sized_detection(100), pose=_standing_pose(), calibration=cam_a)

    # cam-b has seen nothing yet — its reference must still be unwarmed,
    # regardless of how much history cam-a has accumulated.
    result = classifier.classify(frame, _child_sized_detection(170), pose=_standing_pose(), calibration=cam_b)
    assert "relative_height" not in result.signals


def test_relative_height_does_not_fire_for_sitting_or_unknown_posture():
    # Real footage (2026-09-08): a seated adult was read as confident CHILD
    # because her seated bounding-box height was compared against a
    # reference that didn't distinguish sitting from standing. Neither side
    # of that comparison may involve an unconfirmed-standing detection —
    # sitting, and posture-unknown (no pose at all), must both abstain, even
    # against a reference that's already warmed up on standing detections.
    calibration = _calibration(with_reference_points=False)
    classifier = HeuristicAgeClassifier()
    frame = np.zeros((10, 10, 3), dtype=np.uint8)

    for _ in range(20):
        classifier.classify(frame, _child_sized_detection(100), pose=_standing_pose(), calibration=calibration)

    sitting_result = classifier.classify(frame, _child_sized_detection(170), pose=_sitting_pose(), calibration=calibration)
    assert "relative_height" not in sitting_result.signals

    no_pose_result = classifier.classify(frame, _child_sized_detection(170), pose=None, calibration=calibration)
    assert "relative_height" not in no_pose_result.signals


def test_uniform_crop_uses_pose_landmarks_not_fixed_fraction():
    # Real footage (2026-09-08): the fixed-fraction crop bands (15-45% top,
    # 55-85% bottom of box height) were tuned loosely for adult proportions
    # and sample a child's *hair*, not their shirt — a child's head is a far
    # bigger share of their box height than an adult's. This frame's real
    # shirt (white) sits at 30-70% of box height, below where a child's much
    # bigger head ends and where the fixed fraction would still be sampling
    # head/hair. With shoulder/hip/ankle landmarks available, the crop must
    # follow them to the real shirt/shorts regions instead.
    calibration = _calibration(with_reference_points=False)
    detection = Detection(x1=10, y1=0, x2=90, y2=200, confidence=0.9)
    frame = np.zeros((200, 100, 3), dtype=np.uint8)
    frame[60:140, 10:90] = 255  # the real shirt band — white top, everything else stays black

    pose = PoseResult(
        keypoints={
            "left_shoulder": (-10, 60, 1.0), "right_shoulder": (10, 60, 1.0),
            "left_hip": (-10, 140, 1.0), "right_hip": (10, 140, 1.0),
            "left_ankle": (-10, 190, 1.0), "right_ankle": (10, 190, 1.0),
        }
    )
    with_pose = HeuristicAgeClassifier().classify(frame, detection, pose=pose, calibration=calibration)
    assert with_pose.signals.get("appearance") == UNIFORM_MATCH_SCORE

    without_pose = HeuristicAgeClassifier().classify(frame, detection, pose=None, calibration=calibration)
    assert "appearance" not in without_pose.signals


def test_turned_head_rejects_foreshortened_ear_ratio():
    # Real footage (2026-09-08): a child with a turned/profile head was read
    # as confident ADULT — the turn foreshortens ear-to-ear distance in 2D
    # without changing shoulder width, so the ratio looks adult-shaped even
    # though the head is a normal child size. A turned head visibly offsets
    # the ear-midpoint from the shoulder-midpoint (the near ear dominates
    # the average); this must be detected and the ratio rejected rather than
    # trusted at face value.
    calibration = _calibration(with_reference_points=False)
    detection = Detection(x1=0, y1=0, x2=80, y2=60, confidence=0.9)
    turned_head_pose = PoseResult(
        keypoints={
            "left_ear": (28, 5, 1.0), "right_ear": (42, 5, 1.0),  # head width 14, midpoint x=35
            "left_shoulder": (-25, 20, 1.0), "right_shoulder": (25, 20, 1.0),  # shoulder midpoint x=0
        }
    )
    result = HeuristicAgeClassifier().classify(FRAME, detection, pose=turned_head_pose, calibration=calibration)
    assert "pose" not in result.signals
    assert result.adult_score == 0.5
