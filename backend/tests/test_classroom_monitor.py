"""Case 6: a camera going offline must surface as CAMERA_OFFLINE and must
NOT be treated as / confused with UNSUPERVISED."""
from __future__ import annotations

import pytest

from app.events.event_bus import Event, EventBus
from app.events.event_types import EventType
from app.supervision.engine import ClassroomMonitor
from app.supervision.state_machine import SupervisionState


@pytest.mark.asyncio
async def test_camera_offline_does_not_trigger_unsupervised():
    bus = EventBus()
    received: list[Event] = []

    async def capture(event: Event) -> None:
        received.append(event)

    for et in EventType:
        bus.subscribe(et, capture)

    monitor = ClassroomMonitor(
        classroom_id="class-1",
        camera_id="cam-1",
        event_bus=bus,
        unsupervised_delay_seconds=10.0,
        adult_grace_period_seconds=3.0,
        camera_offline_timeout_seconds=5.0,
    )

    await monitor.process_frame(timestamp=0, adult_count=1, child_count=3, unknown_count=0)
    assert monitor.state_machine.state == SupervisionState.SUPERVISED

    await monitor.mark_camera_offline(timestamp=1)
    assert monitor.camera_online is False
    # supervision state is frozen — still SUPERVISED, never flipped to UNSUPERVISED
    assert monitor.state_machine.state == SupervisionState.SUPERVISED

    offline_events = [e for e in received if e.type == EventType.CAMERA_OFFLINE]
    unsupervised_events = [e for e in received if e.type == EventType.UNSUPERVISED_DETECTED]
    assert len(offline_events) == 1
    assert len(unsupervised_events) == 0

    await monitor.mark_camera_online(timestamp=2)
    online_events = [e for e in received if e.type == EventType.CAMERA_ONLINE]
    # one for the initial connect (the first process_frame() call above,
    # since camera_online starts False) and one for this reconnect
    assert len(online_events) == 2


@pytest.mark.asyncio
async def test_unsupervised_event_emitted_on_confirmation():
    bus = EventBus()
    received: list[Event] = []

    async def capture(event: Event) -> None:
        received.append(event)

    bus.subscribe(EventType.UNSUPERVISED_DETECTED, capture)
    bus.subscribe(EventType.SUPERVISION_RESTORED, capture)

    monitor = ClassroomMonitor(
        classroom_id="class-1",
        camera_id="cam-1",
        event_bus=bus,
        unsupervised_delay_seconds=10.0,
        adult_grace_period_seconds=3.0,
        camera_offline_timeout_seconds=5.0,
    )

    await monitor.process_frame(timestamp=0, adult_count=0, child_count=5, unknown_count=0)
    await monitor.process_frame(timestamp=10.1, adult_count=0, child_count=5, unknown_count=0)

    assert any(e.type == EventType.UNSUPERVISED_DETECTED for e in received)

    await monitor.process_frame(timestamp=15, adult_count=1, child_count=5, unknown_count=0)
    assert any(e.type == EventType.SUPERVISION_RESTORED for e in received)


@pytest.mark.asyncio
async def test_unknown_labeled_people_still_count_as_needing_supervision():
    # The classifier only needs to get ADULT right — anyone it can't
    # confidently call an adult (label CHILD or UNKNOWN) must still count as
    # "someone here who needs a supervising adult". This must not read as
    # EMPTY just because nobody was confidently labeled CHILD.
    bus = EventBus()
    received: list[Event] = []

    async def capture(event: Event) -> None:
        received.append(event)

    bus.subscribe(EventType.UNSUPERVISED_DETECTED, capture)

    monitor = ClassroomMonitor(
        classroom_id="class-1",
        camera_id="cam-1",
        event_bus=bus,
        unsupervised_delay_seconds=10.0,
        adult_grace_period_seconds=3.0,
        camera_offline_timeout_seconds=5.0,
    )

    result = await monitor.process_frame(timestamp=0, adult_count=0, child_count=0, unknown_count=6)
    assert result.state != SupervisionState.EMPTY

    result = await monitor.process_frame(timestamp=10.1, adult_count=0, child_count=0, unknown_count=6)
    assert result.state == SupervisionState.UNSUPERVISED
    assert any(e.type == EventType.UNSUPERVISED_DETECTED for e in received)


@pytest.mark.asyncio
async def test_no_people_at_all_stays_empty_no_alert():
    bus = EventBus()
    received: list[Event] = []

    async def capture(event: Event) -> None:
        received.append(event)

    for et in EventType:
        bus.subscribe(et, capture)

    monitor = ClassroomMonitor(
        classroom_id="class-1",
        camera_id="cam-1",
        event_bus=bus,
        unsupervised_delay_seconds=10.0,
        adult_grace_period_seconds=3.0,
        camera_offline_timeout_seconds=5.0,
    )

    result = await monitor.process_frame(timestamp=0, adult_count=0, child_count=0, unknown_count=0)
    assert result.state == SupervisionState.EMPTY

    result = await monitor.process_frame(timestamp=20, adult_count=0, child_count=0, unknown_count=0)
    assert result.state == SupervisionState.EMPTY
    assert not any(e.type == EventType.UNSUPERVISED_DETECTED for e in received)
