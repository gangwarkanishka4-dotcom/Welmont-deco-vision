"""Draws the debug/snapshot overlay: bounding boxes (adults only — see below)
with smoothed confidence, and a status banner. Shared by the live-view
MJPEG/WS stream, the debug overlay, and alert snapshots — no facial identity
information is ever drawn, only track_id + age-group label (spec §12/§26).

Only ADULT-labeled people *inside the ROI* get a drawn box (2026-09-08/09):
children are still fully detected, classified, and counted upstream in the
pipeline exactly as before — this function is purely the visual render and
has no bearing on adult_count/child_count or supervision state. It just
never draws a box or label on a child, or on anyone outside the ROI (who
isn't counted toward adult_count either, so drawing them would falsely
imply a supervising adult who isn't actually affecting the room's status).

Deliberately does NOT draw the ROI polygon itself (2026-09-15) — that outline
is only relevant while actually configuring it, which the Camera
Configuration screen already draws client-side, on its own canvas, straight
from the same ROI data this function never touches. Burning it into the live
feed/snapshots as well showed it to every viewer permanently, not just
whoever's editing it. Recorded incident clips were never affected either
way — they're written from the raw pre-overlay frame (see
CameraWorker.ring_buffer.push in pipeline.py), never from this function's
output."""
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
) -> np.ndarray:
    canvas = frame.copy()

    for person in people:
        # Only adults get a drawn box — children's boxes/labels are never
        # rendered here, even though classification and counting for them
        # still run exactly as before (this function is purely visual; it
        # has no bearing on adult_count/child_count or supervision state,
        # which are all computed upstream in the pipeline before this is
        # ever called). Per request 2026-09-08: no visual boxes on children.
        if person["label"] != "ADULT":
            continue
        # An ADULT outside the ROI doesn't count toward adult_count either
        # (pipeline.py only counts in_roi detections) — drawing a full box
        # for them anyway falsely implies a counted supervising adult who
        # isn't actually affecting the room's status. Real footage
        # 2026-09-09: a confidently-ADULT, out-of-ROI detection (someone at
        # a doorway/hallway edge) drew a full box while genuinely not
        # supervising the room.
        if not person.get("in_roi", True):
            continue

        x1, y1, x2, y2 = (int(v) for v in person["box"])
        color = LABEL_COLORS.get(person["label"], (200, 200, 200))
        cv2.rectangle(canvas, (x1, y1), (x2, y2), color, 2)
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
