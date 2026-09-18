"""CameraWorker: the per-camera async loop that is Phase 1-7 wired together.

    RTSP capture → ring buffer (clip pre-roll)
                 → detector (throttled to INFERENCE_FPS)
                 → tracker (every processed frame)
                 → classifier + rolling history (throttled further via
                   CLASSIFICATION_EVERY_N_DETECT — classification is the
                   most expensive step per spec §19, so it runs less often
                   than detection while the rolling window still smooths
                   over the gap)
                 → ROI containment
                 → ClassroomMonitor.process_frame (supervision state machine)
                 → TRACKED_STATE_UPDATE event (drives the live-view overlay
                   and debug panel over WebSocket)

Blocking calls (cv2 capture, model inference) are pushed to worker threads via
asyncio.to_thread so one slow/offline camera never stalls the event loop that
every other camera and the WebSocket layer share.

Occupancy reconciliation: when a gate line is configured, day-to-day counting
comes from low-latency crossing events (_inside_ids), not per-frame ROI
containment. That's fast but stateful, and state built up incrementally can
drift — a crossing missed to a tracker glitch mis-states occupancy until
something corrects it, and a fresh (re)connect starts that state at zero even
if the room is already occupied. Every OCCUPANCY_RECONCILE_INTERVAL_SECONDS
(and immediately on every (re)connect), _process_frame forces a full
classify+ROI pass over every currently-tracked person and overwrites
_inside_ids with that ground truth, bounding how long any drift can persist.
"""
from __future__ import annotations

import asyncio
import logging
import os
import time
from dataclasses import dataclass, field

import cv2
import numpy as np

# Force RTSP-over-TCP: the control handshake (SETUP/PLAY) is TCP regardless, but
# ffmpeg defaults the actual RTP media to UDP, which routinely gets dropped by
# NAT/firewalls on WAN links — the stream then "opens" but every frame read times
# out. Must be set before any cv2.VideoCapture(rtsp://...) call in this process.
os.environ.setdefault("OPENCV_FFMPEG_CAPTURE_OPTIONS", "rtsp_transport;tcp")

from app.config import Settings
from app.cv.calibration.overlay import draw_overlay
from app.cv.calibration.roi import CameraCalibration
from app.cv.classifier.base import AgeGroupClassifier
from app.cv.classifier.rolling_history import AgeLabel, RollingClassificationHistory
from app.cv.detector.base import Detection, PersonDetector
from app.cv.pose.base import PoseEstimator
from app.cv.tracker.base import PersonTracker
from app.cv.zoom_pass import run_zoom_pass
from app.events.event_bus import Event, EventBus
from app.events.event_types import EventType
from app.supervision.engine import ClassroomMonitor
from app.video.clip_writer import ClipWriter
from app.video.ring_buffer import RingBuffer

logger = logging.getLogger(__name__)


@dataclass
class PersonView:
    track_id: int
    box: tuple[float, float, float, float]
    label: str
    confidence: float
    detector_confidence: float
    in_roi: bool


@dataclass
class FrameState:
    people: list[PersonView] = field(default_factory=list)
    supervision_state: str = "EMPTY"
    adult_count: int = 0
    child_count: int = 0
    unknown_count: int = 0
    fps: float = 0.0
    inference_ms: float = 0.0
    updated_at: float = 0.0


class CameraWorker:
    def __init__(
        self,
        camera_id: str,
        classroom_id: str,
        classroom_name: str,
        rtsp_url: str,
        fps: int,
        settings: Settings,
        event_bus: EventBus,
        detector: PersonDetector,
        tracker: PersonTracker,
        classifier: AgeGroupClassifier,
        calibration: CameraCalibration,
        clip_writer: ClipWriter,
        pose_estimator: PoseEstimator | None = None,
    ) -> None:
        self.camera_id = camera_id
        self.classroom_id = classroom_id
        self.classroom_name = classroom_name
        self.rtsp_url = rtsp_url
        self.fps = fps
        self.settings = settings
        self.event_bus = event_bus
        self.detector = detector
        self.tracker = tracker
        self.classifier = classifier
        self.pose_estimator = pose_estimator
        self.calibration = calibration
        self.clip_writer = clip_writer

        self.ring_buffer = RingBuffer(settings.video_buffer_seconds, fps)
        self.history = RollingClassificationHistory(
            settings.classification_window, settings.adult_confidence_threshold, settings.child_confidence_threshold
        )
        self.monitor = ClassroomMonitor(
            classroom_id=classroom_id,
            camera_id=camera_id,
            event_bus=event_bus,
            unsupervised_delay_seconds=settings.unsupervised_delay_seconds,
            adult_grace_period_seconds=settings.adult_grace_period_seconds,
            camera_offline_timeout_seconds=settings.camera_offline_timeout_seconds,
        )

        self.latest_frame: np.ndarray | None = None
        self.state = FrameState()
        self._frames_since_classify = 0
        self._stop = False
        self._cap: cv2.VideoCapture | None = None
        self._track_last_seen: dict[int, float] = {}

        # Gate-crossing footfall state (see app.cv.calibration.roi.CameraCalibration.crossing).
        # Only used once a gate line has been configured for this camera —
        # until then, occupancy falls back to plain ROI containment below.
        self._prev_foot: dict[int, tuple[float, float]] = {}
        self._inside_ids: set[int] = set()

        # Adults confirmed "inside" via gate crossing — persists across
        # frames where that track isn't currently re-detected (occlusion,
        # tracker glitch), unlike adult_count's usual per-frame computation.
        # Only cleared by an actual "exited" crossing or the long
        # adult_presence_timeout_seconds safety net below. See config.py.
        self._inside_adult_ids: set[int] = set()
        self._adult_last_confirmed: dict[int, float] = {}

        # None means "never reconciled yet" — the very next frame processed
        # forces an immediate reconciliation (see _process_frame), so a
        # (re)connect never starts the room off at a false zero. Reset to
        # None again on every successful (re)connect in run().
        self._last_reconcile_at: float | None = None

        # Real bug found live (2026-09-15): reconcile firing on only the
        # single first frame after a reconnect isn't enough — a confirmed
        # adult who simply isn't re-detected on that exact frame (RTSP
        # streams routinely take a frame or two to stabilize right after
        # reopening) falls out of _inside_ids/_inside_adult_ids and stays
        # excluded until the next scheduled reconcile (up to
        # occupancy_reconcile_interval_seconds later) or a genuine gate
        # crossing — while the persistent-adult adult_count override keeps
        # reporting 0 the whole time, actively suppressing the correct raw
        # per-frame classification. A confirmed real adult, correctly
        # classified every single frame, produced a false "no adult"
        # alert this exact way. Keeping the ground-truth reconcile active
        # for a short grace window after every reconnect (not just one
        # frame) gives detection time to restabilize before the window
        # closes. Set in run() on every successful (re)connect.
        self._reconnect_grace_until: float | None = None

        # Periodic digital-zoom pass state (see app.cv.zoom_pass) — only
        # does anything once calibration.zoom_regions is non-empty.
        self._zoom_window_started_at: float | None = None
        self._zoom_pass_frame_counter: int = 0
        self._zoom_region_index: int = 0

    async def run(self) -> None:
        detect_interval = 1.0 / max(1, self.settings.inference_fps)
        last_detect_at = 0.0
        consecutive_failures = 0

        while not self._stop:
            if self._cap is None:
                opened = await asyncio.to_thread(self._open_capture)
                if not opened:
                    await self.monitor.mark_camera_offline(time.time())
                    await asyncio.sleep(min(2.0 ** min(consecutive_failures, 5), 15.0))
                    consecutive_failures += 1
                    continue
                consecutive_failures = 0
                # Force an immediate occupancy reconciliation on the first
                # frame after a (re)connect — see _last_reconcile_at — and
                # keep it active for a short grace window afterward too,
                # since detection can take a frame or two to restabilize
                # post-reconnect (see _reconnect_grace_until).
                self._last_reconcile_at = None
                self._reconnect_grace_until = time.time() + self.settings.reconnect_reconcile_grace_seconds

            ok, frame = await asyncio.to_thread(self._cap.read)
            now = time.time()

            if not ok or frame is None:
                logger.warning("Camera %s frame read failed", self.camera_id)
                self._release_capture()
                # Real bug found live (2026-09-15): this check used to be
                # unconditionally bypassed by a leftover debug tautology,
                # marking the camera OFFLINE (and flipping the dashboard
                # badge) on literally every single failed read — even a
                # one-frame blip on an RTSP-over-internet feed that
                # reconnects a second later. is_stale() already implements
                # the intended debounce (only genuinely stale past
                # camera_offline_timeout_seconds); it just wasn't being
                # consulted.
                if self.monitor.is_stale(now):
                    await self.monitor.mark_camera_offline(now)
                await asyncio.sleep(1.0)
                continue

            self.latest_frame = frame
            self.ring_buffer.push(frame, now)

            if now - last_detect_at >= detect_interval:
                infer_start = time.perf_counter()
                await self._process_frame(frame, now)
                self.state.inference_ms = (time.perf_counter() - infer_start) * 1000.0
                self.state.fps = 1.0 / max(now - last_detect_at, 1e-6) if last_detect_at else 0.0
                last_detect_at = now

    async def _maybe_run_zoom_pass(
        self, frame: np.ndarray, timestamp: float, existing: list[Detection]
    ) -> list[Detection]:
        """See app.cv.zoom_pass. No-op unless this camera has zoom_regions
        configured. Every zoom_pass_interval_seconds, spends the next
        zoom_pass_duration_seconds also running the detector on an
        upscaled crop of one trouble-spot region per eligible frame
        (alternating frames within that window, not every one — the normal
        full-frame pass above always runs regardless, so this only adds
        load, never blocks or slows down base occupancy tracking)."""
        if not self.calibration.zoom_regions:
            return []

        if (
            self._zoom_window_started_at is None
            or timestamp - self._zoom_window_started_at >= self.settings.zoom_pass_interval_seconds
        ):
            self._zoom_window_started_at = timestamp

        in_window = timestamp - self._zoom_window_started_at < self.settings.zoom_pass_duration_seconds
        self._zoom_pass_frame_counter += 1
        if not in_window or self._zoom_pass_frame_counter % 2 != 0:
            return []

        region = self.calibration.zoom_regions[self._zoom_region_index % len(self.calibration.zoom_regions)]
        self._zoom_region_index += 1

        extra = await asyncio.to_thread(
            run_zoom_pass, self.detector, frame, region, self.settings.zoom_pass_upscale, existing
        )
        if extra:
            logger.info(
                "Camera %s: zoom pass on region %s found %d detection(s) the full-frame pass missed",
                self.camera_id, tuple(round(v) for v in region), len(extra),
            )
        return extra

    async def _process_frame(self, frame: np.ndarray, timestamp: float) -> None:
        detections = await asyncio.to_thread(self.detector.detect, frame)
        detections = detections + await self._maybe_run_zoom_pass(frame, timestamp, detections)
        tracks = await asyncio.to_thread(self.tracker.update, detections, timestamp)

        # Periodic occupancy reconciliation: override whatever the gate-
        # crossing tally currently says with a direct, ground-truth scan of
        # everyone the tracker currently sees. Crossing events are fast but
        # can drift (a missed "entered"/"exited" from a tracker glitch
        # mis-states occupancy indefinitely otherwise); this bounds that
        # drift to at most one interval, and — since _last_reconcile_at
        # starts (and resets on reconnect) as None — also fires on the very
        # first frame, so people already in the room at launch are counted
        # immediately instead of the crossing tally defaulting to zero.
        # Also stays active through the post-reconnect grace window (see
        # _reconnect_grace_until) rather than just the single first frame —
        # detection can take a frame or two to restabilize after an RTSP
        # stream reopens, and a confirmed adult who isn't re-detected on
        # that exact one frame would otherwise fall out of the gate-crossing
        # tally until the next scheduled reconcile, up to
        # occupancy_reconcile_interval_seconds later.
        do_reconcile = (
            self._last_reconcile_at is None
            or timestamp - self._last_reconcile_at >= self.settings.occupancy_reconcile_interval_seconds
            or (self._reconnect_grace_until is not None and timestamp < self._reconnect_grace_until)
        )

        self._frames_since_classify += 1
        do_classify = self._frames_since_classify >= self.settings.classification_every_n_detect or do_reconcile
        if do_classify:
            self._frames_since_classify = 0

        poses = [None] * len(tracks)
        if do_classify and self.pose_estimator is not None and tracks:
            boxes = [t.detection.as_xyxy() for t in tracks]
            poses = await asyncio.to_thread(self.pose_estimator.estimate, frame, boxes)

        people: list[PersonView] = []
        adult_count = child_count = unknown_count = 0
        active_ids = set()

        for i, track in enumerate(tracks):
            active_ids.add(track.track_id)
            self._track_last_seen[track.track_id] = timestamp
            in_roi = self.calibration.contains_detection(track.detection)

            if do_classify:
                result = self.classifier.classify(frame, track.detection, poses[i], self.calibration)
                self.history.update(track.track_id, result.adult_score, track.detection.confidence)

            classification = self.history.get_state(track.track_id)
            label = classification.label.value
            logger.debug(
                "Track ID=%d %s confidence=%.2f in_roi=%s (camera=%s)",
                track.track_id, label, classification.smoothed_adult_score, in_roi, self.camera_id,
            )

            # Gate-based directional footfall: only count a track as "inside
            # the classroom" once it has actually crossed the configured
            # gate line (not merely because it appears somewhere in the ROI).
            # Until a gate is drawn for this camera, fall back to plain ROI
            # containment so nothing regresses.
            counts_toward_occupancy = in_roi
            if self.calibration.is_gate_configured():
                foot = track.detection.foot_point
                prev_foot = self._prev_foot.get(track.track_id)
                if prev_foot is not None:
                    crossing = self.calibration.crossing(prev_foot, foot)
                    if crossing == "entered":
                        self._inside_ids.add(track.track_id)
                        await self._publish_gate_event(EventType.PERSON_ENTERED, track, classification, timestamp)
                    elif crossing == "exited":
                        self._inside_ids.discard(track.track_id)
                        # An actual exit is the one thing that should remove a
                        # persistently-counted adult immediately, regardless
                        # of what their classification happens to read on the
                        # way out (mid-stride poses are noisy).
                        self._inside_adult_ids.discard(track.track_id)
                        self._adult_last_confirmed.pop(track.track_id, None)
                        await self._publish_gate_event(EventType.PERSON_EXITED, track, classification, timestamp)
                self._prev_foot[track.track_id] = foot

                if do_reconcile:
                    # Ground truth for anyone the tracker currently sees:
                    # exactly whether they're in the ROI right now, not
                    # whatever the incremental crossing tally accumulated to.
                    # A track not present this frame at all (occluded,
                    # briefly lost) is left untouched — reconciliation only
                    # corrects people it can actually see this instant.
                    if in_roi:
                        self._inside_ids.add(track.track_id)
                    else:
                        self._inside_ids.discard(track.track_id)

                counts_toward_occupancy = in_roi and track.track_id in self._inside_ids

                # Persistent adult presence: someone genuinely confirmed
                # inside (via gate crossing, same requirement as _inside_ids
                # generally — merely appearing in the ROI without ever
                # crossing the gate still doesn't count, same as before) who
                # reads as ADULT stays counted even on frames where they
                # aren't currently re-detected (occlusion, tracker glitch) —
                # only an "exited" crossing above, or the long
                # adult_presence_timeout_seconds safety net in the cleanup
                # loop below, removes them. This is what stops a momentarily-
                # occluded teacher from flipping the room to UNSUPERVISED
                # just because this exact frame didn't re-detect them.
                #
                # Real bug found live (2026-09-15, Basement Class 2): a
                # continuously-detected adult's smoothed_adult_score hovered
                # right at the 0.75 threshold (0.48-0.85 within ~10s — a bent/
                # seated pose, not occlusion), so classification.label
                # flickered ADULT<->UNKNOWN every few frames. The old `else`
                # branch below discarded her from _inside_adult_ids on every
                # single UNKNOWN frame, instantly zeroing adult_count and
                # firing repeated real false UNSUPERVISED alerts even though
                # she never left the room. Only a confident *opposite* signal
                # (CHILD) should clear persisted-adult status immediately —
                # that protects against a recycled track ID landing on a
                # genuinely different, smaller person (see
                # test_reclassified_as_child_is_not_persisted_as_adult).
                # UNKNOWN is "not sure", not "not an adult", so it leaves her
                # persisted status untouched and lets the long safety-net
                # timeout be the only thing that can evict a merely-noisy
                # classification.
                if track.track_id in self._inside_ids:
                    if classification.label == AgeLabel.ADULT:
                        self._inside_adult_ids.add(track.track_id)
                        self._adult_last_confirmed[track.track_id] = timestamp
                    elif classification.label == AgeLabel.CHILD:
                        self._inside_adult_ids.discard(track.track_id)
                        self._adult_last_confirmed.pop(track.track_id, None)

            if counts_toward_occupancy:
                if classification.label == AgeLabel.ADULT:
                    adult_count += 1
                elif classification.label == AgeLabel.CHILD:
                    child_count += 1
                else:
                    unknown_count += 1

            people.append(
                PersonView(
                    track_id=track.track_id,
                    box=track.detection.as_xyxy(),
                    label=label,
                    # Shown next to the label in the overlay/debug panel as
                    # "how confident is the system in THIS label" — CHILD is
                    # the only label on the opposite side of the 0..1 adult
                    # score, ADULT and UNKNOWN both read the score directly.
                    confidence=(1 - classification.smoothed_adult_score) if classification.label == AgeLabel.CHILD else classification.smoothed_adult_score,
                    detector_confidence=track.detection.confidence,
                    in_roi=in_roi,
                )
            )

        for stale_id in list(self.history.active_track_ids()):
            last_seen = self._track_last_seen.get(stale_id)
            if last_seen is not None and timestamp - last_seen > self.settings.track_timeout_seconds:
                self.history.forget(stale_id)
                self._track_last_seen.pop(stale_id, None)
                if stale_id in self._inside_adult_ids:
                    # This track is a confirmed-inside adult riding out an
                    # occlusion gap longer than track_timeout_seconds (tuned
                    # for classifier bookkeeping, a couple of seconds — far
                    # shorter than a real occlusion). Leave _inside_ids/
                    # _prev_foot alone so that if the tracker keeps the same
                    # ID once they're re-detected, the crossing check above
                    # still sees them as "already inside" instead of reading
                    # their reappearance as never having entered. They still
                    # get evicted by the long adult_presence_timeout_seconds
                    # safety net below if this drags on too long.
                    continue
                # A track that vanished without a matching "exited" gate
                # crossing (tracker lost it, camera glitch, ...) must not
                # permanently inflate the occupancy count.
                self._inside_ids.discard(stale_id)
                self._prev_foot.pop(stale_id, None)

        # Safety net for a presumed-still-inside adult who left without a
        # clean "exited" gate crossing (camera glitch, walked out somewhere
        # the gate line doesn't cover): bounds how long they can stay
        # phantom-counted, without requiring the frequent re-detection the
        # main loop above deliberately no longer demands.
        for adult_id in list(self._inside_adult_ids):
            last_confirmed = self._adult_last_confirmed.get(adult_id)
            if last_confirmed is not None and timestamp - last_confirmed > self.settings.adult_presence_timeout_seconds:
                self._inside_adult_ids.discard(adult_id)
                self._adult_last_confirmed.pop(adult_id, None)
                # Also drop the general _inside_ids entry: once this track has
                # aged out of classification history (the short stale-purge
                # above only spares it while it's still in _inside_adult_ids),
                # nothing else will ever clean this up otherwise, and there's
                # no reason to keep treating them as "inside" for any purpose
                # once we've given up on them here.
                self._inside_ids.discard(adult_id)
                self._prev_foot.pop(adult_id, None)
                logger.info(
                    "Camera %s: track %d dropped from persistent adult presence "
                    "(unconfirmed for over %.0fs — presumed left without a clean exit crossing)",
                    self.camera_id, adult_id, self.settings.adult_presence_timeout_seconds,
                )

        # Once a gate is configured, adult_count reflects who's persistently
        # inside (see above) rather than only who this exact frame
        # re-detected — the entire point of this feature. Cameras without a
        # gate line keep the plain per-frame count computed in the loop.
        if self.calibration.is_gate_configured():
            adult_count = len(self._inside_adult_ids)
            # Real bug found live (2026-09-16): in a busy room, ByteTrack
            # occasionally re-issues a new track ID for the same physical
            # adult (occlusion, a bent-over pose, motion blur). Each new ID
            # gets its own independent 60s grace period once it reads ADULT,
            # so several IDs that all belong to the same one or two real
            # adults can be "persistently inside" at once — live logs showed
            # 9 distinct track IDs read ADULT for one camera within 3
            # minutes, inflating adult_count to 5 in a room with 1-2 real
            # adults. There's no cross-track re-identification here, so the
            # honest bound is: persistent adults can never outnumber the
            # people this exact frame can actually see. Only applied when
            # the tracker sees *someone* — an empty `tracks` list is a
            # detector/frame gap, not evidence the room emptied, and must
            # not zero out a real persisted adult riding out that gap.
            if tracks:
                adult_count = min(adult_count, len(tracks))

        if do_reconcile:
            self._last_reconcile_at = timestamp
            logger.info(
                "Camera %s occupancy reconciled: adult=%d child=%d unknown=%d (%d tracked)",
                self.camera_id, adult_count, child_count, unknown_count, len(tracks),
            )

        # Child-first gating (spec): with no child/unknown present, adult
        # presence is neither counted nor alerted on — the classroom is
        # simply "Class Empty" regardless of how many adults the classifier
        # currently sees.
        if child_count + unknown_count == 0:
            adult_count = 0

        result = await self.monitor.process_frame(timestamp, adult_count, child_count, unknown_count)

        self.state = FrameState(
            people=people,
            supervision_state=result.state.value,
            adult_count=adult_count,
            child_count=child_count,
            unknown_count=unknown_count,
            fps=self.state.fps,
            inference_ms=self.state.inference_ms,
            updated_at=timestamp,
        )

        await self.event_bus.publish(
            Event(
                EventType.TRACKED_STATE_UPDATE,
                {
                    "camera_id": self.camera_id,
                    "classroom_id": self.classroom_id,
                    "state": result.state.value,
                    "adult_count": adult_count,
                    "child_count": child_count,
                    "unknown_count": unknown_count,
                    "people": [
                        {
                            "track_id": p.track_id,
                            "box": p.box,
                            "label": p.label,
                            "confidence": p.confidence,
                            "in_roi": p.in_roi,
                        }
                        for p in people
                    ],
                    "fps": self.state.fps,
                    "inference_ms": self.state.inference_ms,
                    "timestamp": timestamp,
                },
            )
        )

    async def _publish_gate_event(self, event_type: EventType, track, classification, timestamp: float) -> None:
        """Fires once per gate crossing (spec §8): captures the track's
        current best-effort label/height immediately on entry/exit rather
        than waiting — RollingClassificationHistory has already been
        smoothing this track's score every classification cycle, so
        `classification` here reflects a few frames of debouncing, not a
        single noisy read."""
        height_ratio = self.calibration.height_ratio(track.detection)
        estimated_height_cm = (
            round(height_ratio * self.settings.reference_adult_height_cm, 1) if height_ratio is not None else None
        )
        await self.event_bus.publish(
            Event(
                event_type,
                {
                    "camera_id": self.camera_id,
                    "classroom_id": self.classroom_id,
                    "track_id": track.track_id,
                    "label": classification.label.value,
                    "confidence": classification.smoothed_adult_score,
                    "estimated_height_cm": estimated_height_cm,
                    "timestamp": timestamp,
                },
            )
        )

    def render_overlay_jpeg(self) -> bytes | None:
        if self.latest_frame is None:
            return None
        people_dicts = [
            {"box": p.box, "label": p.label, "confidence": p.confidence, "track_id": p.track_id, "in_roi": p.in_roi}
            for p in self.state.people
        ]
        canvas = draw_overlay(self.latest_frame, self.classroom_name, self.state.supervision_state, people_dicts)
        ok, buf = cv2.imencode(".jpg", canvas)
        return buf.tobytes() if ok else None

    def _open_capture(self) -> bool:
        cap = cv2.VideoCapture(self.rtsp_url)
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        if not cap.isOpened():
            cap.release()
            return False
        self._cap = cap
        logger.info("Camera %s stream opened", self.camera_id)
        return True

    def _release_capture(self) -> None:
        if self._cap is not None:
            self._cap.release()
            self._cap = None

    def stop(self) -> None:
        self._stop = True
        self._release_capture()

    # MediaProvider protocol (see app.alerts.alert_manager) ------------------
    def request_incident_clip(self, alert_id: str) -> None:
        tail_seconds = self.settings.video_buffer_seconds
        self.clip_writer.schedule_incident_clip(self.camera_id, alert_id, self.ring_buffer, tail_seconds)
