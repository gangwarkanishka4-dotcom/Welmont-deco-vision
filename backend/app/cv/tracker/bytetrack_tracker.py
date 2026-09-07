"""ByteTrack tracker, backed by the `supervision` package's implementation
(github.com/roboflow/supervision) rather than a hand-rolled Kalman/Hungarian
matcher — same algorithm used across most production YOLO pipelines.

Occlusion tolerance: a track survives `track_timeout_seconds` of consecutive
misses (converted to a frame budget via the configured FPS) before being
dropped, so a person is not "deleted" because detection failed for one or
two frames.
"""
from __future__ import annotations

import time

import numpy as np

from app.cv.detector.base import Detection
from app.cv.tracker.base import PersonTracker, Track


class ByteTrackTracker(PersonTracker):
    def __init__(self, track_timeout_seconds: float = 2.0, fps: int = 12, track_activation_threshold: float = 0.25):
        import supervision as sv

        self._sv = sv
        lost_track_buffer = max(1, round(track_timeout_seconds * fps))
        self.tracker = sv.ByteTrack(
            frame_rate=fps,
            lost_track_buffer=lost_track_buffer,
            track_activation_threshold=track_activation_threshold,
        )
        self.track_timeout_seconds = track_timeout_seconds
        self._first_seen: dict[int, float] = {}
        self._hits: dict[int, int] = {}
        self._last_seen: dict[int, float] = {}

    def reset(self) -> None:
        self.tracker.reset()
        self._first_seen.clear()
        self._hits.clear()
        self._last_seen.clear()

    def update(self, detections: list[Detection], timestamp: float | None = None) -> list[Track]:
        ts = timestamp if timestamp is not None else time.time()
        sv = self._sv

        if detections:
            xyxy = np.array([d.as_xyxy() for d in detections], dtype=np.float32)
            confidence = np.array([d.confidence for d in detections], dtype=np.float32)
            class_id = np.array([d.class_id for d in detections], dtype=int)
        else:
            xyxy = np.zeros((0, 4), dtype=np.float32)
            confidence = np.zeros((0,), dtype=np.float32)
            class_id = np.zeros((0,), dtype=int)

        sv_detections = sv.Detections(xyxy=xyxy, confidence=confidence, class_id=class_id)
        tracked = self.tracker.update_with_detections(sv_detections)

        tracks: list[Track] = []
        current_ids: set[int] = set()
        for i in range(len(tracked)):
            tid = int(tracked.tracker_id[i])
            current_ids.add(tid)
            box = tracked.xyxy[i]
            conf = float(tracked.confidence[i]) if tracked.confidence is not None else 0.0
            cls_id = int(tracked.class_id[i]) if tracked.class_id is not None else 0

            if tid not in self._first_seen:
                self._first_seen[tid] = ts
                self._hits[tid] = 0
            self._hits[tid] += 1
            self._last_seen[tid] = ts

            det = Detection(x1=float(box[0]), y1=float(box[1]), x2=float(box[2]), y2=float(box[3]), confidence=conf, class_id=cls_id)
            tracks.append(
                Track(
                    track_id=tid,
                    detection=det,
                    hits=self._hits[tid],
                    first_seen_at=self._first_seen[tid],
                    last_seen_at=ts,
                )
            )

        # Prune bookkeeping only once a track has been silent for the full
        # timeout window — ByteTrack keeps a tracker_id alive internally
        # (for re-identification after occlusion) up to lost_track_buffer,
        # so we mirror that same grace period here rather than pruning
        # the instant an ID drops out of one frame's output.
        for tid in list(self._first_seen):
            if tid not in current_ids and ts - self._last_seen.get(tid, ts) > self.track_timeout_seconds:
                self._first_seen.pop(tid, None)
                self._hits.pop(tid, None)
                self._last_seen.pop(tid, None)

        return tracks
