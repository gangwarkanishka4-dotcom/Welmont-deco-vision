"""Camera credentials are stored as separate host/port/path/username/password
fields (password encrypted at rest via app.core.crypto) rather than a single
RTSP URL string — a raw URL can't safely round-trip a password containing
'@' or ':' (rtsp://user:p@ss@word@host is ambiguous), and separate fields let
the API return everything except the secret without string-surgery."""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base, UTCDateTime
from app.models.enums import CameraStatus


class Camera(Base):
    __tablename__ = "cameras"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    classroom_id: Mapped[str] = mapped_column(ForeignKey("classrooms.id"), nullable=False, index=True)

    rtsp_host: Mapped[str] = mapped_column(String(255), nullable=False)
    rtsp_port: Mapped[int] = mapped_column(Integer, default=554)
    rtsp_path: Mapped[str] = mapped_column(String(500), default="")
    rtsp_username: Mapped[str] = mapped_column(String(255), default="")
    rtsp_password_encrypted: Mapped[str] = mapped_column(String(500), default="")

    fps: Mapped[int] = mapped_column(Integer, default=25)
    resolution_width: Mapped[int] = mapped_column(Integer, default=1920)
    resolution_height: Mapped[int] = mapped_column(Integer, default=1080)

    status: Mapped[CameraStatus] = mapped_column(String(20), default=CameraStatus.OFFLINE.value, index=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)

    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), server_default=func.now(), onupdate=func.now())

    classroom: Mapped["Classroom"] = relationship(back_populates="cameras")  # noqa: F821
    configuration: Mapped["CameraConfiguration"] = relationship(  # noqa: F821
        back_populates="camera", uselist=False, cascade="all, delete-orphan"
    )

    def build_rtsp_url(self, password: str) -> str:
        from urllib.parse import quote

        auth = ""
        if self.rtsp_username:
            user = quote(self.rtsp_username, safe="")
            pwd = quote(password, safe="") if password else ""
            auth = f"{user}:{pwd}@" if pwd else f"{user}@"
        path = self.rtsp_path if self.rtsp_path.startswith("/") else f"/{self.rtsp_path}"
        return f"rtsp://{auth}{self.rtsp_host}:{self.rtsp_port}{path}"
