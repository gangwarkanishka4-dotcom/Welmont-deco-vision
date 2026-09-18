"""Digital zoom pass (2026-09-14): crop+upscale a known trouble-spot region
and re-run the detector on it, to catch small/seated people who read under
the detector's confidence threshold at native resolution. These tests cover
the pure coordinate-mapping and dedup logic in app.cv.zoom_pass directly —
no real detector or video needed."""
from __future__ import annotations

import numpy as np

from app.cv.detector.base import Detection
from app.cv.zoom_pass import crop_and_upscale, find_new_detections, map_to_frame_coords, run_zoom_pass


def _det(x1, y1, x2, y2, conf=0.9) -> Detection:
    return Detection(x1=x1, y1=y1, x2=x2, y2=y2, confidence=conf)


def test_crop_and_upscale_produces_enlarged_region():
    frame = np.zeros((720, 1280, 3), dtype=np.uint8)
    crop = crop_and_upscale(frame, (100, 100, 200, 150), upscale=2.0)
    assert crop is not None
    assert crop.shape[1] == 200  # (200-100)*2
    assert crop.shape[0] == 100  # (150-100)*2


def test_crop_and_upscale_returns_none_for_degenerate_region():
    frame = np.zeros((720, 1280, 3), dtype=np.uint8)
    assert crop_and_upscale(frame, (500, 500, 500, 600), upscale=2.0) is None  # zero width
    assert crop_and_upscale(frame, (2000, 2000, 2100, 2100), upscale=2.0) is None  # fully off-frame


def test_map_to_frame_coords_undoes_upscale_and_reapplies_offset():
    # A box at (20,20)-(60,60) in a 2x-upscaled crop of region (100,100,200,200)
    # should map back to (110,110)-(130,130) in the original frame.
    zoomed = [_det(20, 20, 60, 60)]
    mapped = map_to_frame_coords(zoomed, region=(100, 100, 200, 200), upscale=2.0)
    assert len(mapped) == 1
    assert mapped[0].x1 == 110
    assert mapped[0].y1 == 110
    assert mapped[0].x2 == 130
    assert mapped[0].y2 == 130
    assert mapped[0].confidence == zoomed[0].confidence


def test_find_new_detections_drops_ones_that_overlap_existing():
    existing = [_det(100, 100, 200, 300)]  # someone the full-frame pass already found
    zoomed_same_person = [_det(105, 105, 205, 305)]  # same person, slightly different box from the zoom crop
    zoomed_new_person = [_det(500, 500, 560, 620)]  # genuinely someone else, e.g. a seated adult it missed

    new = find_new_detections(zoomed_same_person + zoomed_new_person, existing, iou_threshold=0.3)

    assert len(new) == 1
    assert new[0].x1 == 500


def test_find_new_detections_keeps_everything_when_nothing_overlaps():
    existing: list[Detection] = []
    zoomed = [_det(10, 10, 50, 90), _det(200, 200, 260, 340)]
    assert find_new_detections(zoomed, existing) == zoomed


class _FakeDetector:
    """Returns one fixed-size box roughly centered in whatever crop it's given
    — stands in for "the detector confidently finds someone once they're
    enlarged enough", without needing a real model."""

    def __init__(self, box_frac=(0.3, 0.3, 0.7, 0.9), confidence=0.8):
        self.box_frac = box_frac
        self.confidence = confidence

    def detect(self, frame):
        h, w = frame.shape[:2]
        fx1, fy1, fx2, fy2 = self.box_frac
        return [Detection(x1=w * fx1, y1=h * fy1, x2=w * fx2, y2=h * fy2, confidence=self.confidence)]


def test_run_zoom_pass_end_to_end_finds_a_missed_person():
    frame = np.zeros((720, 1280, 3), dtype=np.uint8)
    region = (900, 200, 1150, 450)  # e.g. the Basement Class 1 doorway trouble spot
    detector = _FakeDetector()

    new = run_zoom_pass(detector, frame, region, upscale=2.5, existing=[])

    assert len(new) == 1
    # The found box must land back inside the original region, not still in
    # the upscaled crop's own coordinate space.
    assert region[0] <= new[0].x1 <= region[2]
    assert region[1] <= new[0].y1 <= region[3]


def test_run_zoom_pass_returns_nothing_for_a_degenerate_region():
    frame = np.zeros((720, 1280, 3), dtype=np.uint8)
    detector = _FakeDetector()
    assert run_zoom_pass(detector, frame, (2000, 2000, 2100, 2100), upscale=2.5, existing=[]) == []


# --- CameraWorker-level: timing, interleaving, and region cycling ---------

import tempfile

import pytest

from app.config import Settings
from app.cv.calibration.roi import CameraCalibration
from app.events.event_bus import EventBus
from app.video.clip_writer import ClipWriter
from app.workers.pipeline import CameraWorker

FRAME = np.zeros((720, 1280, 3), dtype=np.uint8)
REGION_A = (900.0, 200.0, 1150.0, 450.0)
REGION_B = (400.0, 380.0, 560.0, 520.0)


class _CountingZoomDetector:
    """Every call to detect() finds one fixed box — used here purely to
    count how many times (and with what crop size) the zoom pass actually
    invokes the detector, not to validate detection content (that's covered
    by the pure-function tests above)."""

    def __init__(self):
        self.call_shapes: list[tuple[int, int]] = []

    def detect(self, frame):
        self.call_shapes.append(frame.shape[:2])
        h, w = frame.shape[:2]
        return [Detection(x1=w * 0.3, y1=h * 0.3, x2=w * 0.7, y2=h * 0.9, confidence=0.8)]


def _zoom_worker(zoom_regions, interval=60.0, duration=10.0, upscale=2.0) -> tuple[CameraWorker, _CountingZoomDetector]:
    calibration = CameraCalibration(camera_id="cam-1", roi_polygon=[], zoom_regions=zoom_regions)
    settings = Settings(
        zoom_pass_interval_seconds=interval,
        zoom_pass_duration_seconds=duration,
        zoom_pass_upscale=upscale,
    )
    detector = _CountingZoomDetector()
    worker = CameraWorker(
        camera_id="cam-1",
        classroom_id="class-1",
        classroom_name="Test Room",
        rtsp_url="rtsp://unused",
        fps=12,
        settings=settings,
        event_bus=EventBus(),
        detector=detector,
        tracker=None,
        classifier=None,
        calibration=calibration,
        clip_writer=ClipWriter(storage_dir=tempfile.mkdtemp(), retention_days=1, fps=12),
    )
    return worker, detector


@pytest.mark.asyncio
async def test_zoom_pass_is_a_complete_noop_without_configured_regions():
    worker, detector = _zoom_worker(zoom_regions=[])
    extra = await worker._maybe_run_zoom_pass(FRAME, timestamp=1000.0, existing=[])
    assert extra == []
    assert detector.call_shapes == []


@pytest.mark.asyncio
async def test_zoom_pass_only_fires_inside_the_window_and_alternates_frames():
    worker, detector = _zoom_worker(zoom_regions=[REGION_A], interval=60.0, duration=10.0)

    # First frame opens a window (t=1000) but the alternating-frame counter
    # starts at 1 (odd) -> skipped this frame.
    await worker._maybe_run_zoom_pass(FRAME, timestamp=1000.0, existing=[])
    assert detector.call_shapes == []

    # Second frame inside the same window (t=1001, still < 1010) -> counter
    # is now even -> the zoom pass actually runs.
    extra = await worker._maybe_run_zoom_pass(FRAME, timestamp=1001.0, existing=[])
    assert len(extra) == 1
    assert len(detector.call_shapes) == 1

    # Long after the window closed (t=1030, interval hasn't elapsed yet
    # either) -> no-op. The counter still increments even though this call
    # is skipped (it's a plain per-call counter, not reset per window) — it's
    # now at 3 (odd).
    await worker._maybe_run_zoom_pass(FRAME, timestamp=1030.0, existing=[])
    assert len(detector.call_shapes) == 1  # unchanged

    # A new window opens once the interval elapses (t=1061 >= 1000+60). This
    # is the 4th call overall -> counter is even -> runs immediately, on the
    # window's very first frame.
    extra2 = await worker._maybe_run_zoom_pass(FRAME, timestamp=1061.0, existing=[])
    assert len(extra2) == 1
    assert len(detector.call_shapes) == 2


@pytest.mark.asyncio
async def test_zoom_pass_crops_and_upscales_the_configured_region():
    worker, detector = _zoom_worker(zoom_regions=[REGION_A], duration=10.0, upscale=2.0)

    await worker._maybe_run_zoom_pass(FRAME, timestamp=1000.0, existing=[])  # skipped (odd)
    await worker._maybe_run_zoom_pass(FRAME, timestamp=1001.0, existing=[])  # runs

    expected_w = int((REGION_A[2] - REGION_A[0]) * 2.0)
    expected_h = int((REGION_A[3] - REGION_A[1]) * 2.0)
    assert detector.call_shapes == [(expected_h, expected_w)]


@pytest.mark.asyncio
async def test_zoom_pass_cycles_through_multiple_regions_on_successive_eligible_frames():
    worker, detector = _zoom_worker(zoom_regions=[REGION_A, REGION_B], duration=10.0, upscale=2.0)

    await worker._maybe_run_zoom_pass(FRAME, timestamp=1000.0, existing=[])  # skipped (odd)
    await worker._maybe_run_zoom_pass(FRAME, timestamp=1001.0, existing=[])  # region A
    await worker._maybe_run_zoom_pass(FRAME, timestamp=1002.0, existing=[])  # skipped (odd)
    await worker._maybe_run_zoom_pass(FRAME, timestamp=1003.0, existing=[])  # region B

    shape_a = (int((REGION_A[3] - REGION_A[1]) * 2.0), int((REGION_A[2] - REGION_A[0]) * 2.0))
    shape_b = (int((REGION_B[3] - REGION_B[1]) * 2.0), int((REGION_B[2] - REGION_B[0]) * 2.0))
    assert detector.call_shapes == [shape_a, shape_b]


@pytest.mark.asyncio
async def test_zoom_pass_drops_a_detection_that_duplicates_an_existing_one():
    worker, detector = _zoom_worker(zoom_regions=[REGION_A], duration=10.0)
    # _CountingZoomDetector always "finds" a box at the same relative
    # position within whatever crop it's given, which maps back inside
    # REGION_A — pre-seed `existing` with that same real-world box so the
    # zoom pass has nothing new to contribute.
    x1, y1, x2, y2 = REGION_A
    w, h = x2 - x1, y2 - y1
    already_found = Detection(x1=x1 + w * 0.3, y1=y1 + h * 0.3, x2=x1 + w * 0.7, y2=y1 + h * 0.9, confidence=0.8)

    await worker._maybe_run_zoom_pass(FRAME, timestamp=1000.0, existing=[already_found])  # skipped (odd)
    extra = await worker._maybe_run_zoom_pass(FRAME, timestamp=1001.0, existing=[already_found])

    assert extra == []
