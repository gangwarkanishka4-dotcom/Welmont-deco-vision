from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base, UTCDateTime


class VideoClip(Base):
    __tablename__ = "video_clips"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    alert_id: Mapped[str | None] = mapped_column(ForeignKey("alerts.alert_id"), nullable=True, index=True)
    camera_id: Mapped[str] = mapped_column(ForeignKey("cameras.id"), nullable=False, index=True)

    file_path: Mapped[str] = mapped_column(String(500), nullable=False)
    started_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    ended_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)

    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), server_default=func.now(), index=True)
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False, index=True)

    alert: Mapped["Alert | None"] = relationship(back_populates="clips")  # noqa: F821
