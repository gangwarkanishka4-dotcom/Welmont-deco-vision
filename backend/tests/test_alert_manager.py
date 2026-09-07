"""Validates spec §29 (dedup: one incident = one alert row, no re-firing
while unsupervised persists) and the buzzer trigger/clear wiring, against a
real (in-memory sqlite) database and the real MockBuzzer — no mocked
detections, just the alert lifecycle itself."""
from __future__ import annotations

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.alerts.alert_manager import AlertManager
from app.config import get_settings
from app.database import Base
from app.events.event_bus import Event, EventBus
from app.events.event_types import EventType
from app.hardware.mock_buzzer import MockBuzzer
from app.models import Alert, Classroom, Camera  # noqa: F401 — registers tables on Base.metadata


@pytest.fixture
async def session_factory():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    yield factory
    await engine.dispose()


@pytest.fixture
async def seeded_camera(session_factory):
    async with session_factory() as session:
        classroom = Classroom(id="class-1", name="Class 2", location="Welmont Lalkothi, Jaipur")
        camera = Camera(id="cam-1", name="Basement Class 1", classroom_id="class-1", rtsp_host="192.0.2.10", rtsp_port=556)
        session.add_all([classroom, camera])
        await session.commit()
    return "cam-1", "class-1"


@pytest.mark.asyncio
async def test_dedup_one_alert_per_incident(session_factory, seeded_camera):
    camera_id, classroom_id = seeded_camera
    bus = EventBus()
    buzzer = MockBuzzer()
    manager = AlertManager(event_bus=bus, session_factory=session_factory, alert_output=buzzer, settings=get_settings())
    manager.register()

    payload = {
        "camera_id": camera_id,
        "classroom_id": classroom_id,
        "incident_id": "INC-abc123",
        "children_count": 8,
        "adult_count": 0,
    }

    # simulate the classroom monitor firing UNSUPERVISED_DETECTED repeatedly
    # while the incident is ongoing (e.g. every frame) — must create exactly one row
    for _ in range(5):
        await bus.publish(Event(EventType.UNSUPERVISED_DETECTED, dict(payload)))

    async with session_factory() as session:
        rows = (await session.scalars(select(Alert).where(Alert.incident_id == "INC-abc123"))).all()

    assert len(rows) == 1
    assert rows[0].status == "ACTIVE"
    assert buzzer.active_alerts == {rows[0].alert_id}


@pytest.mark.asyncio
async def test_resolve_clears_buzzer_and_new_incident_creates_new_alert(session_factory, seeded_camera):
    camera_id, classroom_id = seeded_camera
    bus = EventBus()
    buzzer = MockBuzzer()
    manager = AlertManager(event_bus=bus, session_factory=session_factory, alert_output=buzzer, settings=get_settings())
    manager.register()

    await bus.publish(Event(EventType.UNSUPERVISED_DETECTED, {
        "camera_id": camera_id, "classroom_id": classroom_id, "incident_id": "INC-1", "children_count": 5, "adult_count": 0,
    }))
    assert len(buzzer.active_alerts) == 1

    await bus.publish(Event(EventType.SUPERVISION_RESTORED, {"incident_id": "INC-1", "reason": "adult_returned"}))
    assert len(buzzer.active_alerts) == 0

    async with session_factory() as session:
        resolved = await session.scalar(select(Alert).where(Alert.incident_id == "INC-1"))
    assert resolved.status == "RESOLVED"
    assert resolved.resolved_at is not None

    # adult leaves again later -> genuinely new incident -> new alert row
    await bus.publish(Event(EventType.UNSUPERVISED_DETECTED, {
        "camera_id": camera_id, "classroom_id": classroom_id, "incident_id": "INC-2", "children_count": 5, "adult_count": 0,
    }))

    async with session_factory() as session:
        all_alerts = (await session.scalars(select(Alert))).all()
    assert len(all_alerts) == 2
    assert len(buzzer.active_alerts) == 1
