"""Trained adult/child appearance classifier — plug in once you have labeled
classroom crops (see README "How to train a better adult/child model").

Expected model contract: a single-label binary classifier (adult=1, child=0)
exported as .pt (torchvision-style, loaded via torch.load + eval) or .onnx,
taking a fixed-size RGB crop and returning a probability. Wire the exact
preprocessing to match how you trained it — the defaults below (224x224,
ImageNet normalization) match a typical torchvision classifier head and are
meant to be edited when a real model is supplied.
"""
from __future__ import annotations

import logging

import numpy as np

from app.cv.calibration.roi import CameraCalibration
from app.cv.classifier.base import AgeGroupClassifier, FrameClassification
from app.cv.classifier.heuristic_classifier import HeuristicAgeClassifier
from app.cv.detector.base import Detection
from app.cv.pose.base import PoseResult

logger = logging.getLogger(__name__)

# The appearance model (ml_pipeline/4_train_appearance_model.py) measured
# 94% adult recall / 92% child recall standalone — well above the heuristic
# fallback's real-world performance — so it gets most of the weight. The
# heuristic keeps a small share purely as a sanity check for degenerate
# crops (extreme lighting, corrupted frames) the CNN wasn't trained on.
APPEARANCE_WEIGHT = 0.85
FALLBACK_WEIGHT = 0.15


class MLAgeClassifier(AgeGroupClassifier):
    """Fuses a trained appearance model with the geometry/pose heuristic
    fallback, so classification degrades gracefully if the crop is too small
    or the model is unavailable for a given frame."""

    def __init__(self, model_path: str, device: str = "auto", input_size: int = 224) -> None:
        from app.core.device import resolve_device

        self.device = resolve_device(device)
        self.input_size = input_size
        self.fallback = HeuristicAgeClassifier()
        self._model = self._load(model_path)

    def _load(self, model_path: str):
        try:
            if model_path.endswith(".onnx"):
                import onnxruntime as ort

                providers = ["CUDAExecutionProvider", "CPUExecutionProvider"] if "cuda" in self.device else ["CPUExecutionProvider"]
                return ("onnx", ort.InferenceSession(model_path, providers=providers))
            else:
                import torch

                model = torch.load(model_path, map_location=self.device)
                model.eval()
                return ("torch", model)
        except Exception:
            logger.exception("Failed to load age-group model at %s — falling back to heuristic only", model_path)
            return None

    def classify(
        self,
        frame: np.ndarray,
        detection: Detection,
        pose: PoseResult | None,
        calibration: CameraCalibration,
    ) -> FrameClassification:
        fallback_result = self.fallback.classify(frame, detection, pose, calibration)

        appearance_score = self._run_model(frame, detection)
        if appearance_score is None:
            return fallback_result

        fused = APPEARANCE_WEIGHT * appearance_score + FALLBACK_WEIGHT * fallback_result.adult_score
        signals = dict(fallback_result.signals)
        signals["appearance"] = appearance_score
        signals["fused"] = fused
        return FrameClassification(adult_score=fused, signals=signals)

    def _run_model(self, frame: np.ndarray, detection: Detection) -> float | None:
        if self._model is None:
            return None

        import cv2

        x1, y1, x2, y2 = (max(0, int(v)) for v in detection.as_xyxy())
        crop = frame[y1:y2, x1:x2]
        if crop.size == 0:
            return None

        resized = cv2.resize(crop, (self.input_size, self.input_size))
        rgb = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB).astype(np.float32) / 255.0
        mean = np.array([0.485, 0.456, 0.406], dtype=np.float32)
        std = np.array([0.229, 0.224, 0.225], dtype=np.float32)
        normalized = (rgb - mean) / std
        tensor = normalized.transpose(2, 0, 1)[None, ...]  # NCHW

        kind, model = self._model
        try:
            if kind == "onnx":
                input_name = model.get_inputs()[0].name
                output = model.run(None, {input_name: tensor.astype(np.float32)})[0]
                flat = output.reshape(-1)
                # ml_pipeline/4_train_appearance_model.py exports softmax([P(child), P(adult)]) —
                # a 2-class array, not a single sigmoid score. Fall back to a single-value
                # sigmoid-style output (older single-score .onnx contract) if that's what's loaded.
                return float(flat[1]) if flat.shape[0] >= 2 else float(flat[0])
            else:
                import torch

                with torch.no_grad():
                    t = torch.from_numpy(tensor).to(self.device)
                    output = model(t)
                    return float(torch.sigmoid(output).reshape(-1)[0].cpu())
        except Exception:
            logger.exception("Age-group model inference failed for this crop")
            return None
