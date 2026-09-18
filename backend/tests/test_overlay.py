"""Only adults get a drawn box in the rendered overlay (2026-09-08) — this
is a purely visual choice and must not be confused with the classifier
itself, which still fully detects/classifies/counts children upstream."""
from __future__ import annotations

import inspect

import numpy as np

from app.cv.calibration.overlay import LABEL_COLORS, draw_overlay


def test_adult_gets_a_drawn_box():
    frame = np.zeros((100, 100, 3), dtype=np.uint8)
    # y starts at 40, below the status banner drawn over rows 0-34 — a box
    # placed under the banner would get painted over regardless of label.
    people = [{"box": (10, 40, 30, 60), "label": "ADULT", "confidence": 0.9, "track_id": 1, "in_roi": True}]

    canvas = draw_overlay(frame, "Test Room", "SUPERVISED", people)

    assert tuple(canvas[40, 10]) == LABEL_COLORS["ADULT"]


def test_child_gets_no_drawn_box():
    frame = np.zeros((100, 100, 3), dtype=np.uint8)
    people = [{"box": (50, 50, 70, 70), "label": "CHILD", "confidence": 0.9, "track_id": 2, "in_roi": True}]

    canvas = draw_overlay(frame, "Test Room", "SUPERVISED", people)

    # No box drawn anywhere in the child's region — still plain background.
    assert not canvas[50:70, 50:70].any()


def test_unknown_gets_no_drawn_box():
    frame = np.zeros((100, 100, 3), dtype=np.uint8)
    people = [{"box": (50, 50, 70, 70), "label": "UNKNOWN", "confidence": 0.5, "track_id": 3, "in_roi": True}]

    canvas = draw_overlay(frame, "Test Room", "SUPERVISED", people)

    assert not canvas[50:70, 50:70].any()


def test_mixed_group_only_draws_the_adult():
    frame = np.zeros((100, 100, 3), dtype=np.uint8)
    people = [
        {"box": (10, 40, 30, 60), "label": "ADULT", "confidence": 0.9, "track_id": 1, "in_roi": True},
        {"box": (50, 50, 70, 70), "label": "CHILD", "confidence": 0.9, "track_id": 2, "in_roi": True},
    ]

    canvas = draw_overlay(frame, "Test Room", "SUPERVISED", people)

    assert tuple(canvas[40, 10]) == LABEL_COLORS["ADULT"]
    assert not canvas[50:70, 50:70].any()


def test_out_of_roi_adult_gets_no_drawn_box():
    # Real footage 2026-09-09: a confidently-ADULT detection outside the ROI
    # (someone at a doorway/hallway edge) still drew a full box, which
    # falsely implied a counted supervising adult — pipeline.py only counts
    # in_roi detections toward adult_count, so this person isn't actually
    # affecting the room's status at all.
    frame = np.zeros((100, 100, 3), dtype=np.uint8)
    people = [{"box": (10, 40, 30, 60), "label": "ADULT", "confidence": 0.94, "track_id": 342, "in_roi": False}]

    canvas = draw_overlay(frame, "Test Room", "UNSUPERVISED", people)

    assert not canvas[40:60, 10:30].any()


def test_roi_outline_is_never_drawn():
    # 2026-09-15: the ROI outline used to be burned into the live feed/
    # snapshots for every viewer permanently. It's now only ever shown on the
    # Camera Configuration screen (a separate, client-side canvas the
    # frontend draws straight from the same ROI data) — draw_overlay doesn't
    # accept an roi_polygon argument at all anymore, so there's no way to
    # reintroduce it here by accident.
    frame = np.zeros((100, 100, 3), dtype=np.uint8)

    canvas = draw_overlay(frame, "Test Room", "SUPERVISED", [])

    # Nothing but the status banner (rows 0-34) should be non-black.
    assert not canvas[35:, :].any()
    assert "roi_polygon" not in inspect.signature(draw_overlay).parameters
