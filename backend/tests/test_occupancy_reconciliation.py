"""Periodic occupancy reconciliation (2026-09-09): the gate-crossing tally
(_inside_ids) is fast but stateful, and can drift — a crossing event missed
to a tracker glitch mis-states occupancy indefinitely, and a fresh
(re)connect starts that state at zero even if the room is already occupied.
These tests drive CameraWorker._process_frame directly (bypassing the real
RTSP/detector/tracker/pose stack with small scripted fakes) to verify the
reconciliation pass actually corrects both cases, and doesn't fire on every
frame in between.
"""
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

ROI = [(0, 0), (100, 0), (100, 100), (0, 100)]  # a generous square covering all test detections
GATE_LINE = ((0, 50), (100, 50))
GATE_INSIDE_POINT = (50, 90)


class FakeDetector:
    def detect(self, frame):
        return []  # unused — FakeTracker ignores its `detections` argument entirely


class FakeTracker:
    """Returns exactly the Track list it was constructed with, once."""

    def __init__(self, tracks: list[Track]) -> None:
        self._tracks = tracks

    def update(self, detections, timestamp):
        return self._tracks


class FakeClassifier:
    """Adult-likeness score is smuggled in via Detection.confidence — 0.9
    for "confidently adult", 0.1 for "confidently child" — so each scripted
    Track can encode its own intended classification without needing
    track_id plumbed through the classify() signature."""

    def classify(self, frame, detection, pose, calibration):
        return FrameClassification(adult_score=detection.confidence, signals={})


def _adult_track(track_id: int, y: float = 50.0) -> Track:
    det = Detection(x1=40, y1=y - 10, x2=60, y2=y, confidence=0.9)
    return Track(track_id=track_id, detection=det, hits=1, first_seen_at=0.0, last_seen_at=0.0)


def _child_track(track_id: int, y: float = 30.0) -> Track:
    # A permanent "someone to supervise" fixture — the pipeline's child-first
    # gating zeroes adult_count whenever child_count + unknown_count == 0
    # (an all-adult room isn't something to alert on), so every scenario
    # below needs at least one of these for adult_count to be meaningful.
    det = Detection(x1=10, y1=y - 10, x2=20, y2=y, confidence=0.1)
    return Track(track_id=track_id, detection=det, hits=1, first_seen_at=0.0, last_seen_at=0.0)


def _settings(reconcile_interval: float) -> Settings:
    return Settings(
        occupancy_reconcile_interval_seconds=reconcile_interval,
        classification_every_n_detect=1,
        classification_window=1,
        adult_confidence_threshold=0.5,
        child_confidence_threshold=0.5,
        track_timeout_seconds=999.0,
        camera_offline_timeout_seconds=999.0,
        unsupervised_delay_seconds=999.0,
        adult_grace_period_seconds=999.0,
    )


def _worker(tracks: list[Track], reconcile_interval: float = 25.0) -> CameraWorker:
    calibration = CameraCalibration(
        camera_id="cam-1", roi_polygon=ROI, gate_line=GATE_LINE, gate_inside_point=GATE_INSIDE_POINT
    )
    return CameraWorker(
        camera_id="cam-1",
        classroom_id="class-1",
        classroom_name="Test Room",
        rtsp_url="rtsp://unused",
        fps=12,
        settings=_settings(reconcile_interval),
        event_bus=EventBus(),
        detector=FakeDetector(),
        tracker=FakeTracker(tracks),
        classifier=FakeClassifier(),
        calibration=calibration,
        clip_writer=ClipWriter(storage_dir=tempfile.mkdtemp(), retention_days=1, fps=12),
    )


@pytest.mark.asyncio
async def test_first_frame_ever_reconciles_immediately_not_zero():
    # Cold start: an adult and a child are already standing in the ROI when
    # the worker's very first frame is processed, with no crossing event to
    # have registered either — both must be counted from frame one, not
    # default to zero.
    worker = _worker([_adult_track(1), _child_track(99)])
    assert worker._last_reconcile_at is None

    await worker._process_frame(frame=object(), timestamp=1000.0)

    assert worker.state.adult_count == 1
    assert worker.state.child_count == 1
    assert {1, 99} <= worker._inside_ids


@pytest.mark.asyncio
async def test_reconciliation_corrects_a_missed_crossing():
    # Simulates real drift: the child (99) is already properly registered as
    # inside (steady state), but the adult (7) sits inside the ROI with no
    # "entered" event ever registered for them — e.g. a tracker glitch
    # swallowed the crossing. Once a reconciliation is due, the direct ROI
    # scan must correct the adult's count; it must not be correct already.
    worker = _worker([_adult_track(7), _child_track(99)])
    worker._last_reconcile_at = 1000.0  # reconciled recently, not due yet
    worker._inside_ids = {99}  # child already registered; adult's crossing was missed

    await worker._process_frame(frame=object(), timestamp=1000.1)
    assert worker.state.adult_count == 0  # confirms the drift: not counted without a crossing
    assert worker.state.child_count == 1  # sanity: the child's own count isn't affected

    # Now the reconciliation interval has elapsed.
    await worker._process_frame(frame=object(), timestamp=1030.0)

    assert worker.state.adult_count == 1
    assert 7 in worker._inside_ids


@pytest.mark.asyncio
async def test_crossing_based_tally_used_between_reconciliations():
    # Immediately after a reconciliation, a brand new adult appears inside
    # the ROI but hasn't crossed the gate (no prior foot position to compare
    # against) — normal crossing-based behavior applies: not yet counted.
    # This confirms reconciliation doesn't just always force-count everyone
    # in the ROI on every frame, only at its own interval.
    worker = _worker([_adult_track(3), _child_track(99)])
    await worker._process_frame(frame=object(), timestamp=1000.0)  # first frame: reconciles, counts 3 and 99
    assert worker.state.adult_count == 1

    worker.tracker._tracks = [_adult_track(3), _child_track(99), _adult_track(9)]  # a second adult appears
    await worker._process_frame(frame=object(), timestamp=1000.1)  # well inside the 25s interval — not due

    assert worker.state.adult_count == 1  # track 3 still counted (already in _inside_ids); track 9 is not
    assert 9 not in worker._inside_ids


@pytest.mark.asyncio
async def test_reconnect_resets_reconcile_timer_to_force_immediate_recheck():
    worker = _worker([_adult_track(1)])
    await worker._process_frame(frame=object(), timestamp=1000.0)
    assert worker._last_reconcile_at == 1000.0

    worker._last_reconcile_at = None  # what run() does on every successful (re)connect
    await worker._process_frame(frame=object(), timestamp=1000.2)  # far under the 25s interval

    assert worker._last_reconcile_at == 1000.2  # reconciled anyway, because of the reconnect reset
