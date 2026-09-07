from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class ClassroomCreate(BaseModel):
    name: str
    location: str = ""


class ClassroomOut(BaseModel):
    id: str
    name: str
    location: str | None
    created_at: datetime

    model_config = {"from_attributes": True}
