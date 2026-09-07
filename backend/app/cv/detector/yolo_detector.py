"""Ultralytics YOLO backed person detector. Supports .pt / .onnx / .engine
weights transparently — Ultralytics dispatches on file extension internally."""
from __future__ import annotations

import logging

import numpy as np

from app.core.device import resolve_device
from app.cv.detector.base import Detection, PersonDetector

logger = logging.getLogger(__name__)


class YOLODetector(PersonDetector):
    def __init__(
        self,
        model_path: str,
        device: str = "auto",
        conf_threshold: float = 0.4,
        iou_threshold: float = 0.45,
        class_ids: list[int] | None = None,
    ) -> None:
        from ultralytics import YOLO  # imported lazily so unit tests don't require torch/ultralytics

        self.device = resolve_device(device)
        self.conf_threshold = conf_threshold
        self.iou_threshold = iou_threshold
        self.class_ids = class_ids if class_ids is not None else [0]

        logger.info("Loading person detector %s on device %s", model_path, self.device)
        self.model = YOLO(model_path)
        try:
            self.model.to(self.device)
        except Exception:  # noqa: BLE001 - some exported formats (onnx/engine) manage their own device
            logger.debug("Model does not support .to(device); relying on its own runtime")

    def warmup(self) -> None:
        dummy = np.zeros((640, 640, 3), dtype=np.uint8)
        self.detect(dummy)

    def detect(self, frame: np.ndarray) -> list[Detection]:
        results = self.model.predict(
            frame,
            conf=self.conf_threshold,
            iou=self.iou_threshold,
            classes=self.class_ids,
            device=self.device,
            verbose=False,
        )

        detections: list[Detection] = []
        if not results:
            return detections

        boxes = results[0].boxes
        if boxes is None:
            return detections

        names = results[0].names
        for box in boxes:
            xyxy = box.xyxy[0].tolist()
            conf = float(box.conf[0])
            cls_id = int(box.cls[0])
            detections.append(
                Detection(
                    x1=xyxy[0],
                    y1=xyxy[1],
                    x2=xyxy[2],
                    y2=xyxy[3],
                    confidence=conf,
                    class_id=cls_id,
                    class_name=names.get(cls_id, "person") if isinstance(names, dict) else "person",
                )
            )
        return detections
