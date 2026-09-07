from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class CameraCreate(BaseModel):
    name: str
    classroom_id: str
    rtsp_host: str
    rtsp_port: int = 554
    rtsp_path: str = ""
    rtsp_username: str = ""
    rtsp_password: str = Field(default="", exclude=True)  # never echoed back
    fps: int = 25
    resolution_width: int = 1920
    resolution_height: int = 1080
    enabled: bool = True


class CameraUpdate(BaseModel):
    name: str | None = None
    rtsp_host: str | None = None
    rtsp_port: int | None = None
    rtsp_path: str | None = None
    rtsp_username: str | None = None
    rtsp_password: str | None = Field(default=None, exclude=True)
    fps: int | None = None
    resolution_width: int | None = None
    resolution_height: int | None = None
    enabled: bool | None = None


class CameraOut(BaseModel):
    """Never includes rtsp_password / rtsp_password_encrypted — credentials
    are write-only from the API's perspective (spec §18: do not expose RTSP
    credentials in frontend responses)."""

    id: str
    name: str
    classroom_id: str
    rtsp_host: str
    rtsp_port: int
    rtsp_path: str
    rtsp_username: str
    fps: int
    resolution_width: int
    resolution_height: int
    status: str
    enabled: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ROIPoint(BaseModel):
    x: float
    y: float


class CalibrationPoint(BaseModel):
    pixel_y: float
    reference_height_px: float


class CameraROIUpdate(BaseModel):
    roi: list[ROIPoint]


class CameraCalibrationUpdate(BaseModel):
    calibration_points: list[CalibrationPoint]
    adult_height_ratio: float | None = None
    child_height_ratio: float | None = None


class CameraConfigurationOut(BaseModel):
    camera_id: str
    roi: list[ROIPoint]
    calibration_points: list[CalibrationPoint]
    adult_height_ratio: float
    child_height_ratio: float
