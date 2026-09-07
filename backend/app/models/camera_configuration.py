from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, JSON, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class CameraConfiguration(Base):
    """Per-camera ROI + perspective calibration + classification thresholds —
    maps directly onto app.cv.calibration.roi.CameraCalibration."""

    __tablename__ = "camera_configurations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    camera_id: Mapped[str] = mapped_column(ForeignKey("cameras.id"), nullable=False, unique=True, index=True)

    roi_polygon: Mapped[list] = mapped_column(JSON, default=list)  # [{"x": .., "y": ..}, ...]
    calibration_points: Mapped[list] = mapped_column(JSON, default=list)  # [{"pixel_y": .., "reference_height_px": ..}]

    adult_height_ratio: Mapped[float] = mapped_column(Float, default=0.85)
    child_height_ratio: Mapped[float] = mapped_column(Float, default=0.60)

    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    camera: Mapped["Camera"] = relationship(back_populates="configuration")  # noqa: F821

    def to_calibration(self):
        from app.cv.calibration.roi import CameraCalibration, ReferencePoint

        return CameraCalibration(
            camera_id=self.camera_id,
            roi_polygon=[(p["x"], p["y"]) for p in self.roi_polygon],
            reference_points=[ReferencePoint(p["pixel_y"], p["reference_height_px"]) for p in self.calibration_points],
            adult_height_ratio=self.adult_height_ratio,
            child_height_ratio=self.child_height_ratio,
        )
