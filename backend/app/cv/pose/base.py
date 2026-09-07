"""Pose estimator interface — an optional signal source for the adult/child
classifier (body proportions) and available to the debug overlay."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

import numpy as np

# COCO-17 keypoint names, indexed as Ultralytics/COCO order them.
COCO_KEYPOINTS = [
    "nose", "left_eye", "right_eye", "left_ear", "right_ear",
    "left_shoulder", "right_shoulder", "left_elbow", "right_elbow",
    "left_wrist", "right_wrist", "left_hip", "right_hip",
    "left_knee", "right_knee", "left_ankle", "right_ankle",
]


@dataclass
class PoseResult:
    keypoints: dict[str, tuple[float, float, float]]  # name -> (x, y, confidence)

    def get(self, name: str, min_confidence: float = 0.3) -> tuple[float, float] | None:
        kp = self.keypoints.get(name)
        if kp is None or kp[2] < min_confidence:
            return None
        return (kp[0], kp[1])


class PoseEstimator(ABC):
    @abstractmethod
    def estimate(self, frame: np.ndarray, boxes: list[tuple[float, float, float, float]]) -> list[PoseResult | None]:
        """One PoseResult (or None if not confidently estimated) per input box, same order."""
        ...
