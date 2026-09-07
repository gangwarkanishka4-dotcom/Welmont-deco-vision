from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class AlertOut(BaseModel):
    alert_id: str
    incident_id: str
    camera_id: str
    classroom_id: str
    type: str
    severity: str
    status: str
    started_at: datetime
    confirmed_at: datetime
    acknowledged_at: datetime | None
    resolved_at: datetime | None
    children_count: int
    adult_count: int
    snapshot_url: str | None
    clip_url: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class AlertEventOut(BaseModel):
    id: str
    alert_id: str
    event_type: str
    message: str
    created_at: datetime

    model_config = {"from_attributes": True}


class ClassroomStatusOut(BaseModel):
    classroom_id: str
    classroom_name: str
    camera_id: str
    camera_status: str  # ONLINE | OFFLINE | DISABLED
    supervision_status: str  # EMPTY | SUPERVISED | WAITING_FOR_ADULT | UNSUPERVISED
    adult_count: int
    child_count: int
    unknown_count: int
    active_alert_id: str | None
