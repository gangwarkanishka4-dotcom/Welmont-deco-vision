"""Retention sweep (2026-09-15): deleting an expired clip's file + DB row
used to leave Alert.clip_url still pointing at that now-gone file — the
dashboard would try to load a 404 instead of correctly showing "clip not
available". run_retention_sweep now clears it in the same pass.

Also (later the same day): the Alert/AlertEvent rows themselves used to be
kept forever regardless of clip expiry — the Alerts/Incidents pages kept
accumulating history well past the "N days of data" the clips themselves
were bounded to. The sweep now also purges alerts (and any clips they still
have) past the same retention window, on Welmont's explicit request to keep
only a couple of days of data."""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.database import Base
from app.models.alert import Alert
from app.models.alert_event import AlertEvent
from app.models.camera import Camera
from app.models.classroom import Classroom
from app.models.enums import AlertStatus
from app.models.video_clip import VideoClip
from app.video.retention import run_retention_sweep

RETENTION_DAYS = 2


@pytest.fixture
async def session_factory():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    yield factory
    await engine.dispose()


@pytest.fixture(autouse=True)
async def _seed_roster(session_factory):
    async with session_factory() as session:
        session.add(Classroom(id="class-1", name="Class 1"))
        session.add(Camera(id="cam-1", name="Cam 1", classroom_id="class-1", rtsp_host="192.0.2.10"))
        await session.commit()


async def _seed_alert(session_factory, *, started_at, clip_expires_in=None, clip_url=None, clip_file_exists=False, tmp_path):
    alert_id = f"ALT-TEST-{uuid.uuid4().hex[:6]}"
    file_path = tmp_path / f"{alert_id}.mp4"
    if clip_file_exists:
        file_path.write_bytes(b"not a real video, just needs to exist")

    async with session_factory() as session:
        session.add(
            Alert(
                alert_id=alert_id, incident_id=f"INC-{uuid.uuid4().hex[:6]}", camera_id="cam-1",
                classroom_id="class-1", started_at=started_at, confirmed_at=started_at,
                status=AlertStatus.RESOLVED.value, clip_url=clip_url,
            )
        )
        session.add(AlertEvent(alert_id=alert_id, event_type="CREATED", message=""))
        if clip_expires_in is not None:
            session.add(
                VideoClip(
                    alert_id=alert_id, camera_id="cam-1", file_path=str(file_path),
                    started_at=started_at, ended_at=started_at, expires_at=started_at + clip_expires_in,
                )
            )
        await session.commit()
    return alert_id, file_path


@pytest.mark.asyncio
async def test_sweep_clears_the_alerts_clip_url_when_its_clip_expires(session_factory, tmp_path):
    now = datetime.now(timezone.utc)
    alert_id, file_path = await _seed_alert(
        session_factory, started_at=now, clip_expires_in=timedelta(seconds=-1),
        clip_url="/media/clips/x.mp4", clip_file_exists=True, tmp_path=tmp_path,
    )

    result = await run_retention_sweep(session_factory, RETENTION_DAYS)

    assert result == {"clips": 1, "alerts": 0}
    assert not file_path.exists()
    async with session_factory() as session:
        assert (await session.scalars(select(VideoClip))).first() is None
        alert = await session.get(Alert, alert_id)
        assert alert is not None  # recent alert itself is kept, only its clip expired
        assert alert.clip_url is None


@pytest.mark.asyncio
async def test_sweep_leaves_unexpired_clips_and_their_alert_untouched(session_factory, tmp_path):
    now = datetime.now(timezone.utc)
    alert_id, file_path = await _seed_alert(
        session_factory, started_at=now, clip_expires_in=timedelta(days=2),
        clip_url="/media/clips/x.mp4", clip_file_exists=True, tmp_path=tmp_path,
    )

    result = await run_retention_sweep(session_factory, RETENTION_DAYS)

    assert result == {"clips": 0, "alerts": 0}
    assert file_path.exists()
    async with session_factory() as session:
        alert = await session.get(Alert, alert_id)
        assert alert.clip_url == "/media/clips/x.mp4"


@pytest.mark.asyncio
async def test_sweep_deletes_alerts_past_the_retention_window(session_factory, tmp_path):
    old = datetime.now(timezone.utc) - timedelta(days=RETENTION_DAYS + 1)
    alert_id, file_path = await _seed_alert(
        session_factory, started_at=old, clip_expires_in=timedelta(days=30),  # clip itself not yet expired
        clip_url="/media/clips/x.mp4", clip_file_exists=True, tmp_path=tmp_path,
    )

    result = await run_retention_sweep(session_factory, RETENTION_DAYS)

    assert result == {"clips": 1, "alerts": 1}
    assert not file_path.exists()  # the alert's own clip is removed too, not just expired-by-itself clips
    async with session_factory() as session:
        assert await session.get(Alert, alert_id) is None
        assert (await session.scalars(select(AlertEvent).where(AlertEvent.alert_id == alert_id))).first() is None


@pytest.mark.asyncio
async def test_sweep_keeps_alerts_within_the_retention_window(session_factory, tmp_path):
    recent = datetime.now(timezone.utc) - timedelta(hours=12)
    alert_id, _ = await _seed_alert(session_factory, started_at=recent, tmp_path=tmp_path)

    result = await run_retention_sweep(session_factory, RETENTION_DAYS)

    assert result == {"clips": 0, "alerts": 0}
    async with session_factory() as session:
        assert await session.get(Alert, alert_id) is not None


@pytest.mark.asyncio
async def test_sweep_deletes_a_clipless_old_alert_too(session_factory, tmp_path):
    # An alert whose clip already expired earlier (clip_url already None) —
    # confirms the alert itself still gets purged on its own age, not just
    # as a side effect of clip cleanup.
    old = datetime.now(timezone.utc) - timedelta(days=RETENTION_DAYS + 1)
    alert_id, _ = await _seed_alert(session_factory, started_at=old, tmp_path=tmp_path)

    result = await run_retention_sweep(session_factory, RETENTION_DAYS)

    assert result == {"clips": 0, "alerts": 1}
    async with session_factory() as session:
        assert await session.get(Alert, alert_id) is None
