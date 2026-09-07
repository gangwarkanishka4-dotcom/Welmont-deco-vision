"""Tracker interface. A tracker consumes per-frame detections and returns
persistent tracks with stable IDs across frames, tolerating brief occlusion."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from app.cv.detector.base import Detection


@dataclass
class Track:
    track_id: int
    detection: Detection
    age_frames: int = 0  # total frames this track has existed
    time_since_update: float = 0.0  # seconds since last matched detection
    hits: int = 0  # total number of successful detection matches
    first_seen_at: float = 0.0
    last_seen_at: float = 0.0
    extra: dict = field(default_factory=dict)  # scratch space for classifier state, etc.


class PersonTracker(ABC):
    @abstractmethod
    def update(self, detections: list[Detection], timestamp: float) -> list[Track]:
        """Feed one frame's detections (may be empty) and return the current
        set of *confirmed* live tracks. Implementations own occlusion
        tolerance / track timeout internally."""
        ...

    @abstractmethod
    def reset(self) -> None:
        ...
