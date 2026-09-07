"""Per-camera ROI + perspective calibration.

Deliberately NOT a single global pixel-height threshold: `expected_adult_height_px`
interpolates from admin-supplied reference points so a person's apparent size
is judged relative to *where in the frame* they are standing, not an absolute
pixel count.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from app.cv.detector.base import Detection


@dataclass(frozen=True)
class ReferencePoint:
    """One calibration sample: at this pixel row, a person of known real-world
    height would measure `reference_height_px` tall in the image."""

    pixel_y: float
    reference_height_px: float


def point_in_polygon(point: tuple[float, float], polygon: list[tuple[float, float]]) -> bool:
    """Standard ray-casting point-in-polygon test. Returns True on/near edges
    treated as inside to avoid boundary flicker."""
    if len(polygon) < 3:
        return False

    x, y = point
    inside = False
    n = len(polygon)
    j = n - 1
    for i in range(n):
        xi, yi = polygon[i]
        xj, yj = polygon[j]
        intersects = ((yi > y) != (yj > y)) and (x < (xj - xi) * (y - yi) / (yj - yi + 1e-12) + xi)
        if intersects:
            inside = not inside
        j = i
    return inside


@dataclass
class CameraCalibration:
    camera_id: str
    roi_polygon: list[tuple[float, float]] = field(default_factory=list)
    reference_points: list[ReferencePoint] = field(default_factory=list)
    # Ratio of detected_height / expected_adult_height_px above which the
    # geometry signal leans strongly "adult".
    adult_height_ratio: float = 0.85
    # Ratio below which the geometry signal leans strongly "child".
    child_height_ratio: float = 0.60

    def is_calibrated(self) -> bool:
        return len(self.reference_points) >= 2

    def is_roi_configured(self) -> bool:
        return len(self.roi_polygon) >= 3

    def contains_point(self, point: tuple[float, float]) -> bool:
        """If no ROI has been configured yet, treat the whole frame as the
        classroom (fail-open on setup, not fail-closed on supervision)."""
        if not self.is_roi_configured():
            return True
        return point_in_polygon(point, self.roi_polygon)

    def contains_detection(self, detection: Detection) -> bool:
        return self.contains_point(detection.foot_point)

    def expected_adult_height_px(self, pixel_y: float) -> float | None:
        """Linear interpolation (with edge extrapolation) across the
        admin-supplied reference points, ordered by pixel row."""
        if not self.reference_points:
            return None
        points = sorted(self.reference_points, key=lambda p: p.pixel_y)
        if len(points) == 1:
            return points[0].reference_height_px

        if pixel_y <= points[0].pixel_y:
            a, b = points[0], points[1]
        elif pixel_y >= points[-1].pixel_y:
            a, b = points[-2], points[-1]
        else:
            a, b = points[0], points[-1]
            for i in range(len(points) - 1):
                if points[i].pixel_y <= pixel_y <= points[i + 1].pixel_y:
                    a, b = points[i], points[i + 1]
                    break

        if b.pixel_y == a.pixel_y:
            return a.reference_height_px

        t = (pixel_y - a.pixel_y) / (b.pixel_y - a.pixel_y)
        return a.reference_height_px + t * (b.reference_height_px - a.reference_height_px)

    def height_ratio(self, detection: Detection) -> float | None:
        expected = self.expected_adult_height_px(detection.foot_point[1])
        if not expected or expected <= 0:
            return None
        return detection.height / expected

    def to_dict(self) -> dict:
        return {
            "camera_id": self.camera_id,
            "roi": [{"x": p[0], "y": p[1]} for p in self.roi_polygon],
            "calibration_points": [
                {"pixel_y": p.pixel_y, "reference_height_px": p.reference_height_px} for p in self.reference_points
            ],
            "adult_height_ratio": self.adult_height_ratio,
            "child_height_ratio": self.child_height_ratio,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "CameraCalibration":
        return cls(
            camera_id=data["camera_id"],
            roi_polygon=[(p["x"], p["y"]) for p in data.get("roi", [])],
            reference_points=[
                ReferencePoint(p["pixel_y"], p["reference_height_px"]) for p in data.get("calibration_points", [])
            ],
            adult_height_ratio=data.get("adult_height_ratio", 0.85),
            child_height_ratio=data.get("child_height_ratio", 0.60),
        )
