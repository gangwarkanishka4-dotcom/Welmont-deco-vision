"""Ultralytics YOLO-Pose backed estimator."""
from __future__ import annotations

import logging

import numpy as np

from app.core.device import resolve_device
from app.cv.pose.base import COCO_KEYPOINTS, PoseEstimator, PoseResult

logger = logging.getLogger(__name__)


class YOLOPoseEstimator(PoseEstimator):
    def __init__(self, model_path: str, device: str = "auto", conf_threshold: float = 0.3) -> None:
        from ultralytics import YOLO

        self.device = resolve_device(device)
        self.conf_threshold = conf_threshold
        logger.info("Loading pose model %s on device %s", model_path, self.device)
        self.model = YOLO(model_path)

    def estimate(self, frame: np.ndarray, boxes: list[tuple[float, float, float, float]]) -> list[PoseResult | None]:
        if not boxes:
            return []

        results = self.model.predict(frame, conf=self.conf_threshold, device=self.device, verbose=False)
        if not results or results[0].keypoints is None:
            return [None] * len(boxes)

        kp_result = results[0]
        pred_boxes = kp_result.boxes.xyxy.tolist() if kp_result.boxes is not None else []
        all_keypoints = kp_result.keypoints.data.tolist()  # [N, 17, 3]

        outputs: list[PoseResult | None] = []
        for box in boxes:
            best_idx, best_iou = None, 0.0
            for i, pbox in enumerate(pred_boxes):
                iou = _iou(box, tuple(pbox))
                if iou > best_iou:
                    best_iou, best_idx = iou, i

            if best_idx is None or best_iou < 0.3:
                outputs.append(None)
                continue

            kps = all_keypoints[best_idx]
            keypoint_map = {name: (kps[i][0], kps[i][1], kps[i][2]) for i, name in enumerate(COCO_KEYPOINTS)}
            outputs.append(PoseResult(keypoints=keypoint_map))

        return outputs


def _iou(a: tuple[float, float, float, float], b: tuple[float, float, float, float]) -> float:
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b
    ix1, iy1 = max(ax1, bx1), max(ay1, by1)
    ix2, iy2 = min(ax2, bx2), min(ay2, by2)
    iw, ih = max(0.0, ix2 - ix1), max(0.0, iy2 - iy1)
    inter = iw * ih
    area_a = max(0.0, ax2 - ax1) * max(0.0, ay2 - ay1)
    area_b = max(0.0, bx2 - bx1) * max(0.0, by2 - by1)
    union = area_a + area_b - inter
    return inter / union if union > 0 else 0.0
