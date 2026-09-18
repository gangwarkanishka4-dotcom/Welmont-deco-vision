"""Reconnect reconcile grace window (2026-09-15): a real false alert traced
back to this exact sequence — camera drops for a few seconds, reconnects,
and by the time the ground-truth reconcile fires (previously: only the
single first frame back), the two real, continuously-correctly-classified
adults in the room had somehow fallen out of _inside_ids/_inside_adult_ids —
so the reconcile's own "ground truth" pass, seeing no one from its tracked
history in that set, read adult=0 and an alert fired despite every frame's
raw classification correctly reading ADULT once people were visible again.

Whatever the exact prior sequence that emptied the set, the fix is the same
either way: reconcile is a ground-truth *correction* — it only has a chance
to fix the count on frames where it's actually active, and it doesn't help
if the very person it needs to see isn't detected on that one specific
frame. Extending it across a short grace window after every reconnect,
instead of just the first frame back, gives detection time to restabilize
before the window closes."""
from __future__ import annotations

import tempfile

import pytest

from app.config import Settings
from app.cv.calibration.roi import CameraCalibration
from app.cv.classifier.base import FrameClassification
from app.cv.detector.base import Detection
from app.cv.tracker.base import Track
from app.events.event_bus import EventBus
from app.video.clip_writer import ClipWriter
from app.workers.pipeline import CameraWorker

ROI = [(0, 0), (100, 0), (100, 100), (0, 100)]
GATE_LINE = ((0, 50), (100, 50))
GATE_INSIDE_POINT = (50, 90)


class FakeDetector:
    def detect(self, frame):
        return []


class FakeTracker:
    def __init__(self, tracks: list[Track]) -> None:
        self._tracks = tracks

    def update(self, detections, timestamp):
        return self._tracks


class FakeClassifier:
    def classify(self, frame, detection, pose, calibration):
        return FrameClassification(adult_score=detection.confidence, signals={})


def _adult_track(track_id: int, y: float = 90.0) -> Track:
    det = Detection(x1=40, y1=y - 10, x2=60, y2=y, confidence=0.9)
    return Track(track_id=track_id, detection=det, hits=1, first_seen_at=0.0, last_seen_at=0.0)


def _child_track(track_id: int, y: float = 30.0) -> Track:
    det = Detection(x1=10, y1=y - 10, x2=20, y2=y, confidence=0.1)
    return Track(track_id=track_id, detection=det, hits=1, first_seen_at=0.0, last_seen_at=0.0)


def _worker(tracks: list[Track], reconnect_grace_seconds: float = 5.0) -> CameraWorker:
    calibration = CameraCalibration(
        camera_id="cam-1", roi_polygon=ROI, gate_line=GATE_LINE, gate_inside_point=GATE_INSIDE_POINT
    )
    settings = Settings(
        occupancy_reconcile_interval_seconds=999_999.0,  # isolate the reconnect-grace behavior specifically
        reconnect_reconcile_grace_seconds=reconnect_grace_seconds,
        classification_every_n_detect=1,
        classification_window=1,
        adult_confidence_threshold=0.5,
        child_confidence_threshold=0.5,
        track_timeout_seconds=2.0,
        camera_offline_timeout_seconds=999.0,
        unsupervised_delay_seconds=999.0,
        adult_grace_period_seconds=999.0,
    )
    return CameraWorker(
        camera_id="cam-1",
        classroom_id="class-1",
        classroom_name="Test Room",
        rtsp_url="rtsp://unused",
        fps=12,
        settings=settings,
        event_bus=EventBus(),
        detector=FakeDetector(),
        tracker=FakeTracker(tracks),
        classifier=FakeClassifier(),
        calibration=calibration,
        clip_writer=ClipWriter(storage_dir=tempfile.mkdtemp(), retention_days=1, fps=12),
    )


@pytest.mark.asyncio
async def test_reappearing_adult_recovered_within_grace_window_even_if_bookkeeping_was_lost():
    worker = _worker([_child_track(99)])

    # Simulate the observed real-world end state right after a reconnect:
    # for whatever reason, the previously-confirmed adult's bookkeeping
    # didn't survive the gap — _inside_ids/_inside_adult_ids don't have
    # them. This is the exact condition that made the real alert's
    # reconcile pass read adult=0.
    worker._reconnect_grace_until = 1000.0 + 5.0
    worker._last_reconcile_at = None

    # First frame back: still just the child, adult not yet re-detected —
    # matches the real incident (detection took a frame or two to catch up).
    await worker._process_frame(frame=object(), timestamp=1000.0)
    assert worker.state.adult_count == 0  # nothing to recover yet — no one's visible

    # The adult reappears a couple of seconds later, still within the grace
    # window. They never physically cross the gate line (same foot position
    # as if they'd been standing there the whole time) — only a still-active
    # ground-truth reconcile, not a crossing event, can pick them back up.
    worker.tracker._tracks = [_adult_track(1), _child_track(99)]
    await worker._process_frame(frame=object(), timestamp=1002.0)

    assert worker.state.adult_count == 1
    assert 1 in worker._inside_ids
    assert 1 in worker._inside_adult_ids


@pytest.mark.asyncio
async def test_same_reappearance_is_not_recovered_once_the_grace_window_has_closed():
    # Control case: confirms the recovery above is actually attributable to
    # the grace window being active, not some other unconditional path —
    # the identical reappearance fails to be picked up once do_reconcile has
    # genuinely gone back to false.
    worker = _worker([_child_track(99)], reconnect_grace_seconds=1.0)
    worker._reconnect_grace_until = 1000.0 + 1.0
    worker._last_reconcile_at = None

    await worker._process_frame(frame=object(), timestamp=1000.0)

    # Reappears well after the (now much shorter) grace window has closed,
    # and after the next scheduled reconcile too (interval is effectively
    # infinite in this test setup) — so nothing forces a ground-truth check.
    worker.tracker._tracks = [_adult_track(1), _child_track(99)]
    await worker._process_frame(frame=object(), timestamp=1005.0)

    assert worker.state.adult_count == 0
    assert 1 not in worker._inside_ids
