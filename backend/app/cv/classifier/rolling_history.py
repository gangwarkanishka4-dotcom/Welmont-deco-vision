"""Per-track rolling classification history.

A single frame's classifier output is never trusted on its own (see spec
§5/§37). Every frame's adult-probability score is pushed into a fixed-size
window per track_id; the *smoothed* average is what actually drives the
ADULT / CHILD / UNKNOWN label.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from enum import Enum


class AgeLabel(str, Enum):
    ADULT = "ADULT"
    CHILD = "CHILD"
    UNKNOWN = "UNKNOWN"


@dataclass
class ClassificationState:
    label: AgeLabel
    smoothed_adult_score: float
    sample_count: int
    history: list[float]


class RollingClassificationHistory:
    def __init__(self, window: int, adult_threshold: float, child_threshold: float) -> None:
        self.window = window
        self.adult_threshold = adult_threshold
        self.child_threshold = child_threshold
        self._scores: dict[int, deque[float]] = {}
        self._weights: dict[int, deque[float]] = {}

    def update(self, track_id: int, adult_score: float, confidence: float = 1.0) -> ClassificationState:
        scores = self._scores.setdefault(track_id, deque(maxlen=self.window))
        weights = self._weights.setdefault(track_id, deque(maxlen=self.window))
        scores.append(max(0.0, min(1.0, adult_score)))
        weights.append(max(1e-3, confidence))
        return self.get_state(track_id)

    def get_state(self, track_id: int) -> ClassificationState:
        scores = self._scores.get(track_id)
        if not scores:
            return ClassificationState(AgeLabel.UNKNOWN, 0.5, 0, [])

        weights = self._weights[track_id]
        total_weight = sum(weights)
        smoothed = sum(s * w for s, w in zip(scores, weights)) / total_weight if total_weight else 0.5

        if smoothed >= self.adult_threshold:
            label = AgeLabel.ADULT
        elif (1.0 - smoothed) >= self.child_threshold:
            label = AgeLabel.CHILD
        else:
            label = AgeLabel.UNKNOWN

        return ClassificationState(label, smoothed, len(scores), list(scores))

    def forget(self, track_id: int) -> None:
        self._scores.pop(track_id, None)
        self._weights.pop(track_id, None)

    def active_track_ids(self) -> list[int]:
        return list(self._scores.keys())
