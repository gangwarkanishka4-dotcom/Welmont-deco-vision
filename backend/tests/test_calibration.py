"""app/cv/calibration/roi.py has zero heavy dependencies (pure python +
dataclasses) but backs a spec-critical requirement: no global pixel-height
threshold, ROI containment must use the foot point, and an unconfigured ROI
must fail OPEN (whole frame counts) rather than fail closed."""
from __future__ import annotations

from app.cv.calibration.roi import CameraCalibration, ReferencePoint, point_in_polygon
from app.cv.detector.base import Detection

SQUARE = [(0, 0), (100, 0), (100, 100), (0, 100)]


def test_point_in_polygon_inside_and_outside():
    assert point_in_polygon((50, 50), SQUARE) is True
    assert point_in_polygon((150, 50), SQUARE) is False
    assert point_in_polygon((-10, 50), SQUARE) is False


def test_unconfigured_roi_fails_open():
    calibration = CameraCalibration(camera_id="cam-1")
    detection = Detection(x1=0, y1=0, x2=10, y2=2000, confidence=0.9)  # far outside any sane polygon
    assert calibration.is_roi_configured() is False
    assert calibration.contains_detection(detection) is True


def test_configured_roi_uses_foot_point_not_centroid():
    calibration = CameraCalibration(camera_id="cam-1", roi_polygon=SQUARE)
    # A tall detection whose CENTER lies outside the ROI but whose foot point
    # (bottom-center) lies inside it — must count as inside.
    detection = Detection(x1=40, y1=-500, x2=60, y2=90, confidence=0.9)
    assert detection.center[1] < 0  # centroid is above the ROI square (y<0)
    assert calibration.contains_detection(detection) is True

    detection_outside = Detection(x1=40, y1=-500, x2=60, y2=150, confidence=0.9)  # foot point y=150, outside
    assert calibration.contains_detection(detection_outside) is False


def test_expected_adult_height_interpolates_between_reference_points():
    calibration = CameraCalibration(
        camera_id="cam-1",
        reference_points=[ReferencePoint(pixel_y=200, reference_height_px=100), ReferencePoint(pixel_y=600, reference_height_px=300)],
    )
    assert calibration.expected_adult_height_px(200) == 100
    assert calibration.expected_adult_height_px(600) == 300
    assert calibration.expected_adult_height_px(400) == 200  # midpoint, linear interpolation


def test_expected_adult_height_extrapolates_at_edges():
    calibration = CameraCalibration(
        camera_id="cam-1",
        reference_points=[ReferencePoint(pixel_y=200, reference_height_px=100), ReferencePoint(pixel_y=600, reference_height_px=300)],
    )
    # beyond either reference point — extrapolates along the same linear
    # slope defined by the two points (100px height per 400px of row, i.e.
    # 0.5 px height per pixel of row), rather than clamping.
    assert calibration.expected_adult_height_px(0) == 0
    assert calibration.expected_adult_height_px(800) == 400


def test_height_ratio_reflects_perspective_not_absolute_pixels():
    """The same real-world adult height should NOT need the same pixel
    height near vs. far from the camera — this is exactly what a naive
    global pixel-height threshold gets wrong (spec §2/§3)."""
    calibration = CameraCalibration(
        camera_id="cam-1",
        reference_points=[ReferencePoint(pixel_y=200, reference_height_px=100), ReferencePoint(pixel_y=600, reference_height_px=300)],
    )
    near_adult = Detection(x1=0, y1=500, x2=50, y2=600, confidence=0.9)  # 100px tall, foot at y=600 -> expected 300
    far_adult = Detection(x1=0, y1=150, x2=50, y2=200, confidence=0.9)  # 50px tall, foot at y=200 -> expected 100

    near_ratio = calibration.height_ratio(near_adult)
    far_ratio = calibration.height_ratio(far_adult)

    assert near_ratio == 100 / 300
    assert far_ratio == 50 / 100
    # a physically shorter person far away (far_ratio) still reads as more
    # "adult-like" in ratio terms than someone genuinely small up close would
    assert far_ratio > near_ratio


def test_no_reference_points_returns_none_not_a_guess():
    calibration = CameraCalibration(camera_id="cam-1")
    detection = Detection(x1=0, y1=0, x2=50, y2=100, confidence=0.9)
    assert calibration.height_ratio(detection) is None
