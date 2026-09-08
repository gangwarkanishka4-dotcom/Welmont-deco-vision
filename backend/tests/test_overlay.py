"""Only adults get a drawn box in the rendered overlay (2026-09-08) — this
is a purely visual choice and must not be confused with the classifier
itself, which still fully detects/classifies/counts children upstream."""
from __future__ import annotations

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
