from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.enums import AlertSeverity, AlertStatus, AlertType


def _alert_id() -> str:
    now = datetime.now(timezone.utc)
    return f"ALT-{now.strftime('%Y%m%d')}-{uuid.uuid4().hex[:6].upper()}"


class Alert(Base):
    __tablename__ = "alerts"

    alert_id: Mapped[str] = mapped_column(String(40), primary_key=True, default=_alert_id)
    incident_id: Mapped[str] = mapped_column(String(40), nullable=False, index=True, unique=True)

    camera_id: Mapped[str] = mapped_column(ForeignKey("cameras.id"), nullable=False, index=True)
    classroom_id: Mapped[str] = mapped_column(ForeignKey("classrooms.id"), nullable=False, index=True)

    type: Mapped[str] = mapped_column(String(40), default=AlertType.UNSUPERVISED_CLASSROOM.value)
    severity: Mapped[str] = mapped_column(String(20), default=AlertSeverity.HIGH.value)
    status: Mapped[str] = mapped_column(String(20), default=AlertStatus.ACTIVE.value, index=True)

    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    confirmed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    children_count: Mapped[int] = mapped_column(Integer, default=0)
    adult_count: Mapped[int] = mapped_column(Integer, default=0)

    snapshot_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    clip_url: Mapped[str | None] = mapped_column(String(500), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)

    events: Mapped[list["AlertEvent"]] = relationship(back_populates="alert", cascade="all, delete-orphan")  # noqa: F821
    clips: Mapped[list["VideoClip"]] = relationship(back_populates="alert")  # noqa: F821
