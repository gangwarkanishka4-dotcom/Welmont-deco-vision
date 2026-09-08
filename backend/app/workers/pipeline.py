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
from app.cv.detector.base import PersonDetector
from app.cv.pose.base import PoseEstimator
from app.cv.tracker.base import PersonTracker
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

            ok, frame = await asyncio.to_thread(self._cap.read)
            now = time.time()

            if not ok or frame is None:
                logger.warning("Camera %s frame read failed", self.camera_id)
                self._release_capture()
                if self.monitor.is_stale(now) or True:
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

    async def _process_frame(self, frame: np.ndarray, timestamp: float) -> None:
        detections = await asyncio.to_thread(self.detector.detect, frame)
        tracks = await asyncio.to_thread(self.tracker.update, detections, timestamp)

        self._frames_since_classify += 1
        do_classify = self._frames_since_classify >= self.settings.classification_every_n_detect
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
                        await self._publish_gate_event(EventType.PERSON_EXITED, track, classification, timestamp)
                self._prev_foot[track.track_id] = foot
                counts_toward_occupancy = in_roi and track.track_id in self._inside_ids

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
                # A track that vanished without a matching "exited" gate
                # crossing (tracker lost it, camera glitch, ...) must not
                # permanently inflate the occupancy count.
                self._inside_ids.discard(stale_id)
                self._prev_foot.pop(stale_id, None)

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
        canvas = draw_overlay(
            self.latest_frame, self.classroom_name, self.state.supervision_state, people_dicts, self.calibration.roi_polygon
        )
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
