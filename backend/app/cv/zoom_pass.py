"""Periodic "digital zoom" detection pass (see Settings.zoom_pass_* and
CameraCalibration.zoom_regions).

The idea: a small/distant/seated person can sit right at the detector's
confidence floor at native resolution simply because their box is small in
pixels — cropping a known trouble spot out of the frame and upscaling it
before running the same detector on just that crop gives the same person a
much larger apparent size, often pushing a borderline detection comfortably
above threshold. This is purely additive to the normal full-frame detection
pass (which keeps running every frame regardless, so occupancy tracking
never stops) — only genuinely new boxes the full-frame pass missed get
merged in, via `find_new_detections`.
"""
from __future__ import annotations

import numpy as np

from app.cv.detector.base import Detection, PersonDetector

ZoomRegion = tuple[float, float, float, float]  # (x1, y1, x2, y2) in native frame coordinates


def crop_and_upscale(frame: np.ndarray, region: ZoomRegion, upscale: float) -> np.ndarray | None:
    """Crop `region` out of `frame` and enlarge it by `upscale`. Returns None
    for a degenerate region (off-frame, zero-area) rather than raising —
    a misconfigured region should never crash the pipeline."""
    import cv2

    h, w = frame.shape[:2]
    x1, y1, x2, y2 = region
    xi1, yi1 = max(0, int(x1)), max(0, int(y1))
    xi2, yi2 = min(w, int(x2)), min(h, int(y2))
    if xi2 <= xi1 or yi2 <= yi1:
        return None

    crop = frame[yi1:yi2, xi1:xi2]
    new_w = max(1, int(crop.shape[1] * upscale))
    new_h = max(1, int(crop.shape[0] * upscale))
    return cv2.resize(crop, (new_w, new_h), interpolation=cv2.INTER_LINEAR)


def map_to_frame_coords(detections: list[Detection], region: ZoomRegion, upscale: float) -> list[Detection]:
    """Map boxes found in the upscaled crop back to native frame coordinates:
    undo the upscale, then re-add the crop's own offset within the frame."""
    x1, y1, _x2, _y2 = region
    mapped = []
    for det in detections:
        mapped.append(
            Detection(
                x1=det.x1 / upscale + x1,
                y1=det.y1 / upscale + y1,
                x2=det.x2 / upscale + x1,
                y2=det.y2 / upscale + y1,
                confidence=det.confidence,
                class_id=det.class_id,
                class_name=det.class_name,
            )
        )
    return mapped


def _iou(a: Detection, b: Detection) -> float:
    ix1, iy1 = max(a.x1, b.x1), max(a.y1, b.y1)
    ix2, iy2 = min(a.x2, b.x2), min(a.y2, b.y2)
    inter = max(0.0, ix2 - ix1) * max(0.0, iy2 - iy1)
    area_a = max(0.0, a.x2 - a.x1) * max(0.0, a.y2 - a.y1)
    area_b = max(0.0, b.x2 - b.x1) * max(0.0, b.y2 - b.y1)
    union = area_a + area_b - inter
    return inter / union if union > 0 else 0.0


def find_new_detections(
    zoomed: list[Detection], existing: list[Detection], iou_threshold: float = 0.3
) -> list[Detection]:
    """Of the (already frame-coordinate-mapped) zoomed-pass detections, keep
    only the ones that don't already substantially overlap something the
    normal full-frame pass found — those are the same real person, already
    correctly tracked, not a new find."""
    return [z for z in zoomed if not any(_iou(z, e) >= iou_threshold for e in existing)]


def run_zoom_pass(
    detector: PersonDetector, frame: np.ndarray, region: ZoomRegion, upscale: float, existing: list[Detection]
) -> list[Detection]:
    """End-to-end: crop+upscale the region, detect, map back, and return only
    the genuinely new detections. Safe to call with a degenerate region."""
    crop = crop_and_upscale(frame, region, upscale)
    if crop is None:
        return []
    zoomed = detector.detect(crop)
    mapped = map_to_frame_coords(zoomed, region, upscale)
    return find_new_detections(mapped, existing)
