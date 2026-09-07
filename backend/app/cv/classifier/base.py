"""Adult/child classifier interface for a *single frame's* single detection.

Temporal smoothing across frames is NOT this class's job — that lives in
RollingClassificationHistory. This class only has to answer: given what I can
see in this one frame, how adult-like is this person? (0 = child-like, 1 =
adult-like). Swap HeuristicAgeClassifier for a trained model by implementing
this same contract — nothing else in the pipeline needs to change.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field

import numpy as np

from app.cv.calibration.roi import CameraCalibration
from app.cv.detector.base import Detection
from app.cv.pose.base import PoseResult


@dataclass
class FrameClassification:
    adult_score: float  # 0..1, fused across whichever signals were available
    signals: dict[str, float] = field(default_factory=dict)  # per-signal breakdown, for debug mode


class AgeGroupClassifier(ABC):
    @abstractmethod
    def classify(
        self,
        frame: np.ndarray,
        detection: Detection,
        pose: PoseResult | None,
        calibration: CameraCalibration,
    ) -> FrameClassification:
        ...
