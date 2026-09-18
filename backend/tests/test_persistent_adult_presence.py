"""Persistent adult presence (2026-09-14): once an adult has genuinely
crossed into the room (confirmed via the gate, the same rule plain
_inside_ids already used), CameraWorker keeps counting them even on frames
where the tracker doesn't currently re-detect them (occlusion, a brief
tracker glitch) — only an actual "exited" gate crossing, or the long
adult_presence_timeout_seconds safety net, removes them. This is what stops a
momentarily-occluded teacher from falsely flipping the room to UNSUPERVISED.
These tests drive CameraWorker._process_frame directly with small scripted
fakes, mirroring test_occupancy_reconciliation.py.
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
GATE_INSIDE_POINT = (50, 90)  # y > 50 is "inside" the classroom


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
    for "confidently adult", 0.1 for "confidently child"."""

    def classify(self, frame, detection, pose, calibration):
        return FrameClassification(adult_score=detection.confidence, signals={})


def _adult_track(track_id: int, y: float = 90.0) -> Track:
    det = Detection(x1=40, y1=y - 10, x2=60, y2=y, confidence=0.9)
    return Track(track_id=track_id, detection=det, hits=1, first_seen_at=0.0, last_seen_at=0.0)


def _child_track(track_id: int, y: float = 30.0) -> Track:
    # A permanent "someone to supervise" fixture — the pipeline's child-first
    # gating zeroes adult_count whenever child_count + unknown_count == 0, so
    # every scenario below needs one of these for adult_count to be meaningful.
    det = Detection(x1=10, y1=y - 10, x2=20, y2=y, confidence=0.1)
    return Track(track_id=track_id, detection=det, hits=1, first_seen_at=0.0, last_seen_at=0.0)


def _worker(
    tracks: list[Track],
    track_timeout_seconds: float = 2.0,
    adult_presence_timeout_seconds: float = 300.0,
    adult_confidence_threshold: float = 0.5,
    child_confidence_threshold: float = 0.5,
) -> CameraWorker:
    calibration = CameraCalibration(
        camera_id="cam-1", roi_polygon=ROI, gate_line=GATE_LINE, gate_inside_point=GATE_INSIDE_POINT
    )
    settings = Settings(
        # Kept far out of range so reconciliation only fires on the very
        # first frame (cold start) and never masks the crossing-based
        # persistence behavior under test here.
        occupancy_reconcile_interval_seconds=999_999.0,
        classification_every_n_detect=1,
        classification_window=1,
        adult_confidence_threshold=adult_confidence_threshold,
        child_confidence_threshold=child_confidence_threshold,
        track_timeout_seconds=track_timeout_seconds,
        adult_presence_timeout_seconds=adult_presence_timeout_seconds,
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
async def test_adult_persists_through_occlusion_gap_shorter_than_presence_timeout():
    worker = _worker([_adult_track(1), _child_track(99)], track_timeout_seconds=2.0)
    await worker._process_frame(frame=object(), timestamp=1000.0)
    assert worker.state.adult_count == 1
    assert 1 in worker._inside_adult_ids

    # Adult drops out of detection entirely (occlusion) for longer than
    # track_timeout_seconds but nowhere near adult_presence_timeout_seconds —
    # only the child is still detected.
    worker.tracker._tracks = [_child_track(99)]
    await worker._process_frame(frame=object(), timestamp=1005.0)  # 5s gap > 2s track_timeout

    assert worker.state.adult_count == 1  # still persisted, not reset to 0
    assert 1 in worker._inside_adult_ids


@pytest.mark.asyncio
async def test_reappearing_track_after_occlusion_still_counts_without_re_crossing():
    worker = _worker([_adult_track(1), _child_track(99)], track_timeout_seconds=2.0)
    await worker._process_frame(frame=object(), timestamp=1000.0)

    worker.tracker._tracks = [_child_track(99)]
    await worker._process_frame(frame=object(), timestamp=1005.0)  # occluded past track_timeout_seconds

    # Same track_id resumes detection, in the same spot (no gate re-crossing).
    # This only stays correct because the earlier stale-track purge is not
    # allowed to evict a confirmed adult's _inside_ids entry — otherwise this
    # reappearance would misread as "never crossed in" and get dropped.
    worker.tracker._tracks = [_adult_track(1), _child_track(99)]
    await worker._process_frame(frame=object(), timestamp=1010.0)

    assert worker.state.adult_count == 1
    assert 1 in worker._inside_ids
    assert 1 in worker._inside_adult_ids


@pytest.mark.asyncio
async def test_exit_crossing_clears_persisted_adult_immediately():
    worker = _worker([_adult_track(1, y=90.0), _child_track(99)], adult_presence_timeout_seconds=300.0)
    await worker._process_frame(frame=object(), timestamp=1000.0)
    assert worker.state.adult_count == 1

    # Foot crosses the gate line outward (inside → outside) between two
    # consecutively-detected frames — a real departure, not an occlusion gap.
    # Must clear immediately, no matter how large adult_presence_timeout_seconds is.
    worker.tracker._tracks = [_adult_track(1, y=10.0), _child_track(99)]
    await worker._process_frame(frame=object(), timestamp=1000.2)

    assert worker.state.adult_count == 0
    assert 1 not in worker._inside_adult_ids
    assert 1 not in worker._inside_ids


@pytest.mark.asyncio
async def test_long_unconfirmed_adult_evicted_by_safety_net_timeout():
    worker = _worker([_adult_track(1), _child_track(99)], adult_presence_timeout_seconds=60.0)
    await worker._process_frame(frame=object(), timestamp=1000.0)
    assert worker.state.adult_count == 1

    # Adult never reappears and never registers an exit crossing (e.g. left
    # through a doorway the gate line doesn't cover) — the child alone stays
    # visible so the room isn't simply reported empty.
    worker.tracker._tracks = [_child_track(99)]
    await worker._process_frame(frame=object(), timestamp=1030.0)  # well under the 60s safety net
    assert worker.state.adult_count == 1  # still presumed present

    await worker._process_frame(frame=object(), timestamp=1061.0)  # past the 60s safety net
    assert worker.state.adult_count == 0
    assert 1 not in worker._inside_adult_ids
    assert 1 not in worker._inside_ids


@pytest.mark.asyncio
async def test_reclassified_as_child_is_not_persisted_as_adult():
    # A track confirmed inside but currently reading CHILD must not linger in
    # _inside_adult_ids just because it was ADULT a moment ago.
    worker = _worker([_adult_track(1), _child_track(99)])
    await worker._process_frame(frame=object(), timestamp=1000.0)
    assert 1 in worker._inside_adult_ids

    worker.tracker._tracks = [_child_track(1), _child_track(99)]
    await worker._process_frame(frame=object(), timestamp=1000.2)

    assert 1 not in worker._inside_adult_ids


@pytest.mark.asyncio
async def test_flickering_unknown_classification_does_not_evict_persisted_adult():
    # Real bug found live (2026-09-15, Basement Class 2): a continuously-
    # detected, genuinely-present adult's smoothed classification hovered
    # right at the confidence threshold (bent/seated pose, not occlusion),
    # flickering ADULT<->UNKNOWN frame to frame. The old code discarded her
    # from _inside_adult_ids on every single UNKNOWN frame, repeatedly
    # zeroing adult_count and firing real false UNSUPERVISED alerts even
    # though she never left the room. UNKNOWN ("not sure") must not clear
    # persisted-adult status the way a confident CHILD reclassification does
    # (see test_reclassified_as_child_is_not_persisted_as_adult above) — only
    # an actual exit crossing or the long safety-net timeout should.
    det_unknown = Detection(x1=40, y1=80.0, x2=60, y2=90.0, confidence=0.6)  # FakeClassifier: adult_score=0.6 -> UNKNOWN at 0.75/0.75

    def _unknown_track(track_id: int) -> Track:
        return Track(track_id=track_id, detection=det_unknown, hits=1, first_seen_at=0.0, last_seen_at=0.0)

    # Thresholds matching production defaults (0.5/0.5 in the other tests here
    # leaves no room for an UNKNOWN band — every score is either confidently
    # ADULT or confidently CHILD, which can't reproduce this bug).
    worker = _worker([_adult_track(1), _child_track(99)], adult_confidence_threshold=0.75, child_confidence_threshold=0.75)
    await worker._process_frame(frame=object(), timestamp=1000.0)
    assert 1 in worker._inside_adult_ids
    assert worker.state.adult_count == 1

    # Same track, still detected every frame, but this frame's classification
    # reads UNKNOWN instead of ADULT (classifier noise around the threshold).
    worker.tracker._tracks = [_unknown_track(1), _child_track(99)]
    await worker._process_frame(frame=object(), timestamp=1000.2)

    assert 1 in worker._inside_adult_ids  # not evicted by a merely-uncertain read
    assert worker.state.adult_count == 1

    # She reads ADULT again a moment later, as real flickering footage does.
    worker.tracker._tracks = [_adult_track(1), _child_track(99)]
    await worker._process_frame(frame=object(), timestamp=1000.4)
    assert worker.state.adult_count == 1


@pytest.mark.asyncio
async def test_phantom_adult_ids_from_track_churn_are_capped_by_visible_headcount():
    # Real bug found live (2026-09-16): in a busy room, ByteTrack occasionally
    # re-issues a new track ID for the same physical adult (occlusion, a
    # bent-over pose, motion blur). Each new ID earns its own independent
    # persistence entry once it reads ADULT, so several IDs belonging to the
    # same one or two real adults can be "persistently inside" at once — live
    # logs showed 9 distinct track IDs read ADULT within 3 minutes on one
    # camera, inflating adult_count to 5 in a room with 1-2 real adults.
    worker = _worker([_adult_track(1), _child_track(99)])
    await worker._process_frame(frame=object(), timestamp=1000.0)
    assert worker.state.adult_count == 1

    # Simulate 3 more track IDs that piled up earlier from exactly this kind
    # of churn — none of them are in this frame's tracker output at all.
    worker._inside_adult_ids.update({2, 3, 4})
    worker._inside_ids.update({2, 3, 4})
    for tid in (2, 3, 4):
        worker._adult_last_confirmed[tid] = 1000.0

    # Only the original adult + one child are actually visible this frame —
    # adult_count must not exceed how many people can actually be seen.
    await worker._process_frame(frame=object(), timestamp=1000.2)
    assert worker.state.adult_count == 2
