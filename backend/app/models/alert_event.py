from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base, UTCDateTime


class AlertEvent(Base):
    """One timeline entry per alert: created / acknowledged / resolved /
    buzzer_triggered / buzzer_cleared — powers the incident detail timeline."""

    __tablename__ = "alert_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    alert_id: Mapped[str] = mapped_column(ForeignKey("alerts.alert_id"), nullable=False, index=True)
    event_type: Mapped[str] = mapped_column(String(50), nullable=False)
    message: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), server_default=func.now(), index=True)

    alert: Mapped["Alert"] = relationship(back_populates="events")  # noqa: F821
