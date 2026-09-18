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
    # Gate/entrance line for directional footfall — two points defining the
    # line, plus a point known to sit on the "inside" (classroom) side.
    gate_line: tuple[tuple[float, float], tuple[float, float]] | None = None
    gate_inside_point: tuple[float, float] | None = None
    # Fixed "digital zoom" trouble spots (x1, y1, x2, y2) in native frame
    # coordinates — see app.cv.zoom_pass and Settings.zoom_pass_*. Empty by
    # default: a camera with no regions configured never runs a zoom pass.
    zoom_regions: list[tuple[float, float, float, float]] = field(default_factory=list)

    def is_calibrated(self) -> bool:
        return len(self.reference_points) >= 2

    def is_roi_configured(self) -> bool:
        return len(self.roi_polygon) >= 3

    def is_gate_configured(self) -> bool:
        return self.gate_line is not None and self.gate_inside_point is not None

    @staticmethod
    def _side(point: tuple[float, float], line: tuple[tuple[float, float], tuple[float, float]]) -> float:
        """Signed area of (a, b, point) — positive on one side of the line
        a->b, negative on the other, zero exactly on it."""
        (ax, ay), (bx, by) = line
        px, py = point
        return (bx - ax) * (py - ay) - (by - ay) * (px - ax)

    def crossing(self, prev_point: tuple[float, float], curr_point: tuple[float, float]) -> str | None:
        """Per-frame foot-point line-crossing test (not a full segment
        intersection — acceptable at the pipeline's tracked-point cadence):
        returns "entered" if the point moved from the outside side of the
        gate line to the inside side between two consecutive frames,
        "exited" for the reverse, or None if no gate is configured or the
        point didn't cross."""
        if not self.is_gate_configured():
            return None

        inside_sign = self._side(self.gate_inside_point, self.gate_line)
        if inside_sign == 0:
            return None  # inside reference point sits on the line itself — misconfigured

        prev_side = self._side(prev_point, self.gate_line)
        curr_side = self._side(curr_point, self.gate_line)
        if prev_side == 0 or curr_side == 0:
            return None  # exactly on the line — wait for a clear frame on either side

        prev_inside = (prev_side > 0) == (inside_sign > 0)
        curr_inside = (curr_side > 0) == (inside_sign > 0)
        if prev_inside == curr_inside:
            return None
        return "entered" if curr_inside else "exited"

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
            "gate_line": [{"x": p[0], "y": p[1]} for p in self.gate_line] if self.gate_line else [],
            "gate_inside_point": (
                {"x": self.gate_inside_point[0], "y": self.gate_inside_point[1]} if self.gate_inside_point else None
            ),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "CameraCalibration":
        gate_line_raw = data.get("gate_line", [])
        gate_inside_raw = data.get("gate_inside_point")
        return cls(
            camera_id=data["camera_id"],
            roi_polygon=[(p["x"], p["y"]) for p in data.get("roi", [])],
            reference_points=[
                ReferencePoint(p["pixel_y"], p["reference_height_px"]) for p in data.get("calibration_points", [])
            ],
            adult_height_ratio=data.get("adult_height_ratio", 0.85),
            child_height_ratio=data.get("child_height_ratio", 0.60),
            gate_line=tuple((p["x"], p["y"]) for p in gate_line_raw) if len(gate_line_raw) == 2 else None,
            gate_inside_point=(gate_inside_raw["x"], gate_inside_raw["y"]) if gate_inside_raw else None,
        )
