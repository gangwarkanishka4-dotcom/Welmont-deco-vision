"""Draws the debug/snapshot overlay: bounding boxes (adults only — see below)
with smoothed confidence, ROI polygon, and a status banner. Shared by the
live-view MJPEG/WS stream, the debug overlay, and alert snapshots — no facial
identity information is ever drawn, only track_id + age-group label (spec §12/§26).

Only ADULT-labeled people get a drawn box (2026-09-08): children are still
fully detected, classified, and counted upstream in the pipeline exactly as
before — this function is purely the visual render and has no bearing on
adult_count/child_count or supervision state. It just never draws a box or
label on a child in the rendered image."""
from __future__ import annotations

from datetime import datetime, timezone

import cv2
import numpy as np

STATE_COLORS = {
    "SUPERVISED": (60, 180, 75),
    "WAITING_FOR_ADULT": (0, 165, 255),
    "UNSUPERVISED": (0, 0, 220),
    "EMPTY": (150, 150, 150),
}
LABEL_COLORS = {"ADULT": (60, 180, 75), "CHILD": (0, 200, 255), "UNKNOWN": (160, 160, 160)}


def draw_overlay(
    frame: np.ndarray,
    classroom_name: str,
    state: str,
    people: list[dict],  # [{"box": (x1,y1,x2,y2), "label": "ADULT", "confidence": 0.94, "track_id": 17, "in_roi": True}]
    roi_polygon: list[tuple[float, float]] | None = None,
) -> np.ndarray:
    canvas = frame.copy()

    if roi_polygon and len(roi_polygon) >= 3:
        pts = np.array(roi_polygon, dtype=np.int32).reshape((-1, 1, 2))
        overlay = canvas.copy()
        cv2.fillPoly(overlay, [pts], (255, 255, 255))
        cv2.addWeighted(overlay, 0.08, canvas, 0.92, 0, canvas)
        cv2.polylines(canvas, [pts], isClosed=True, color=(255, 255, 255), thickness=2)

    for person in people:
        # Only adults get a drawn box — children's boxes/labels are never
        # rendered here, even though classification and counting for them
        # still run exactly as before (this function is purely visual; it
        # has no bearing on adult_count/child_count or supervision state,
        # which are all computed upstream in the pipeline before this is
        # ever called). Per request 2026-09-08: no visual boxes on children.
        if person["label"] != "ADULT":
            continue

        x1, y1, x2, y2 = (int(v) for v in person["box"])
        color = LABEL_COLORS.get(person["label"], (200, 200, 200))
        thickness = 2 if person.get("in_roi", True) else 1
        cv2.rectangle(canvas, (x1, y1), (x2, y2), color, thickness)
        text = f"{person['label']} {person['confidence']*100:.0f}%  #{person['track_id']}"
        (tw, th), _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
        cv2.rectangle(canvas, (x1, max(0, y1 - th - 8)), (x1 + tw + 6, y1), color, -1)
        cv2.putText(canvas, text, (x1 + 3, y1 - 5), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 1, cv2.LINE_AA)

    banner_color = STATE_COLORS.get(state, (100, 100, 100))
    timestamp = datetime.now(timezone.utc).strftime("%H:%M:%S")
    banner_text = f"{classroom_name}   {state}   {timestamp}"
    cv2.rectangle(canvas, (0, 0), (canvas.shape[1], 34), banner_color, -1)
    cv2.putText(canvas, banner_text, (10, 23), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (255, 255, 255), 2, cv2.LINE_AA)

    return canvas
