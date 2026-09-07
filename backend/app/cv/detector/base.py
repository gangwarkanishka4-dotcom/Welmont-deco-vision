"""Detector interface. Swap YOLODetector for any other model by implementing
this contract — nothing downstream (tracker, classifier, engine) depends on
the concrete detector."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class Detection:
    """A single person detection in pixel coordinates for one frame."""

    x1: float
    y1: float
    x2: float
    y2: float
    confidence: float
    class_id: int = 0
    class_name: str = "person"

    @property
    def width(self) -> float:
        return self.x2 - self.x1

    @property
    def height(self) -> float:
        return self.y2 - self.y1

    @property
    def foot_point(self) -> tuple[float, float]:
        """Bottom-center of the box — the point used for ROI containment
        (a person's contact point with the floor), not the box centroid."""
        return ((self.x1 + self.x2) / 2.0, self.y2)

    @property
    def center(self) -> tuple[float, float]:
        return ((self.x1 + self.x2) / 2.0, (self.y1 + self.y2) / 2.0)

    def as_xyxy(self) -> tuple[float, float, float, float]:
        return (self.x1, self.y1, self.x2, self.y2)


class PersonDetector(ABC):
    """Runs person detection on a single BGR frame (as returned by cv2.VideoCapture)."""

    @abstractmethod
    def detect(self, frame: np.ndarray) -> list[Detection]:
        ...

    def warmup(self) -> None:
        """Optional: run one dummy inference to avoid a cold-start latency
        spike on the first real frame. No-op by default."""
        return None
