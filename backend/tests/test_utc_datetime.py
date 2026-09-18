"""UTCDateTime (2026-09-15): SQLite silently drops tzinfo on
DateTime(timezone=True) columns, so a naive datetime comes back on read even
though every write in this codebase is UTC in practice. That naive value
serializes to JSON without a 'Z'/offset, and the frontend's `new Date(...)`
then reads it as *local browser time* instead of UTC — confirmed live
against a real alert whose displayed time was off by exactly the IST/UTC gap
(5.5 hours). This test drives a real SQLite round-trip (not just the
TypeDecorator's Python-level logic) to prove the actual bug stays fixed."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.database import Base
from app.models.alert import Alert
from app.models.camera import Camera
from app.models.classroom import Classroom
from app.models.enums import AlertStatus


@pytest.mark.asyncio
async def test_alert_timestamps_survive_a_real_sqlite_round_trip_as_utc():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    written_at = datetime.now(timezone.utc)
    alert_id = f"ALT-TEST-{uuid.uuid4().hex[:6]}"

    async with session_factory() as session:
        session.add(Classroom(id="class-1", name="Class 1"))
        session.add(Camera(id="cam-1", name="Cam 1", classroom_id="class-1", rtsp_host="192.0.2.10"))
        session.add(
            Alert(
                alert_id=alert_id,
                incident_id=f"INC-{uuid.uuid4().hex[:6]}",
                camera_id="cam-1",
                classroom_id="class-1",
                started_at=written_at,
                confirmed_at=written_at,
                status=AlertStatus.ACTIVE.value,
            )
        )
        await session.commit()

    # A fresh session/query, forcing an actual read off SQLite rather than
    # reusing the in-memory object still attached from the write above.
    async with session_factory() as session:
        alert = await session.scalar(select(Alert).where(Alert.alert_id == alert_id))

    assert alert.started_at.tzinfo is not None
    # isoformat() must carry an explicit UTC offset, or `new Date(...)` on
    # the frontend silently reinterprets it as local time.
    assert alert.started_at.isoformat().endswith("+00:00")
    assert alert.started_at == written_at

    await engine.dispose()
