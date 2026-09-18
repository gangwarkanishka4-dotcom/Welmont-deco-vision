from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Float, ForeignKey, JSON, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base, UTCDateTime


class CameraConfiguration(Base):
    """Per-camera ROI + perspective calibration + classification thresholds —
    maps directly onto app.cv.calibration.roi.CameraCalibration."""

    __tablename__ = "camera_configurations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    camera_id: Mapped[str] = mapped_column(ForeignKey("cameras.id"), nullable=False, unique=True, index=True)

    roi_polygon: Mapped[list] = mapped_column(JSON, default=list)  # [{"x": .., "y": ..}, ...]
    calibration_points: Mapped[list] = mapped_column(JSON, default=list)  # [{"pixel_y": .., "reference_height_px": ..}]

    # Gate/entrance line for directional footfall: two points defining the
    # line, plus one point known to sit on the "inside" (classroom) side —
    # together they let app.cv.calibration.roi.CameraCalibration.crossing()
    # tell an entering crossing from an exiting one.
    gate_line: Mapped[list] = mapped_column(JSON, default=list)  # [{"x": .., "y": ..}, {"x": .., "y": ..}]
    gate_inside_point: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # {"x": .., "y": ..}

    # Fixed "digital zoom" trouble spots for the periodic zoom pass (see
    # app.cv.zoom_pass, Settings.zoom_pass_*) — [{"x1":..,"y1":..,"x2":..,"y2":..}, ...]
    # in native frame coordinates. Empty by default: no regions configured
    # means the zoom pass never runs for this camera.
    zoom_regions: Mapped[list] = mapped_column(JSON, default=list)

    adult_height_ratio: Mapped[float] = mapped_column(Float, default=0.85)
    # Target child height ~92.5cm (spec: 90-95cm) / an assumed 165cm average
    # adult reference height (Settings.reference_adult_height_cm) ≈ 0.56.
    child_height_ratio: Mapped[float] = mapped_column(Float, default=0.56)

    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), server_default=func.now(), onupdate=func.now())

    camera: Mapped["Camera"] = relationship(back_populates="configuration")  # noqa: F821

    def to_calibration(self):
        from app.cv.calibration.roi import CameraCalibration, ReferencePoint

        return CameraCalibration(
            camera_id=self.camera_id,
            roi_polygon=[(p["x"], p["y"]) for p in self.roi_polygon],
            reference_points=[ReferencePoint(p["pixel_y"], p["reference_height_px"]) for p in self.calibration_points],
            adult_height_ratio=self.adult_height_ratio,
            child_height_ratio=self.child_height_ratio,
            gate_line=tuple((p["x"], p["y"]) for p in self.gate_line) if len(self.gate_line) == 2 else None,
            gate_inside_point=(self.gate_inside_point["x"], self.gate_inside_point["y"]) if self.gate_inside_point else None,
            zoom_regions=[(r["x1"], r["y1"], r["x2"], r["y2"]) for r in self.zoom_regions],
        )
