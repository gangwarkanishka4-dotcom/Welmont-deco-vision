"""ClassroomMonitor wires the pure SupervisionStateMachine to the rest of the
system: it turns per-frame person counts into state-machine updates, and
turns state-machine results into events on the bus (which AlertManager,
the WebSocket layer, and the hardware layer all subscribe to independently).

Camera-offline handling lives here, one level above the pure state machine:
while offline, process_frame() is simply never called by the camera worker,
so the underlying SUPERVISED/WAITING/UNSUPERVISED state freezes at its last
known value instead of drifting toward UNSUPERVISED on missing data (spec §25).
"""
from __future__ import annotations

import logging
import time

from app.events.event_bus import Event, EventBus
from app.events.event_types import EventType
from app.supervision.state_machine import SupervisionState, SupervisionStateMachine, SupervisionUpdateResult

logger = logging.getLogger(__name__)


class ClassroomMonitor:
    def __init__(
        self,
        classroom_id: str,
        camera_id: str,
        event_bus: EventBus,
        unsupervised_delay_seconds: float,
        adult_grace_period_seconds: float,
        camera_offline_timeout_seconds: float,
    ) -> None:
        self.classroom_id = classroom_id
        self.camera_id = camera_id
        self.event_bus = event_bus
        self.camera_offline_timeout_seconds = camera_offline_timeout_seconds
        self.state_machine = SupervisionStateMachine(
            classroom_id=classroom_id,
            unsupervised_delay_seconds=unsupervised_delay_seconds,
            adult_grace_period_seconds=adult_grace_period_seconds,
        )
        # Starts False (not True) so that the very first successful frame
        # produces a real False->True transition and fires CAMERA_ONLINE —
        # otherwise nothing downstream (e.g. persisting status to the
        # Camera DB row) ever learns the camera actually came online.
        self.camera_online = False
        self.last_frame_at: float | None = None
        self._previous_state: SupervisionState | None = None

    async def process_frame(
        self,
        timestamp: float,
        adult_count: int,
        child_count: int,
        unknown_count: int,
    ) -> SupervisionUpdateResult:
        self.last_frame_at = timestamp
        if not self.camera_online:
            await self.mark_camera_online(timestamp)

        result = self.state_machine.update(
            timestamp=timestamp,
            # "Someone here who isn't a confirmed adult" — not "someone
            # confirmed as a child". The classifier only needs to get ADULT
            # right; anyone it can't confidently call an adult (CHILD or
            # UNKNOWN) is treated as needing supervision. This is the actual
            # policy: if people are present, is a teacher among them? If
            # nobody is present at all, there's nothing to check.
            children_present=(child_count + unknown_count) > 0,
            adult_present=adult_count > 0,
        )

        base_payload = {
            "camera_id": self.camera_id,
            "classroom_id": self.classroom_id,
            "state": result.state.value,
            "children_count": child_count,
            "adult_count": adult_count,
            "unknown_count": unknown_count,
            "timestamp": timestamp,
        }

        if result.just_confirmed_unsupervised:
            logger.warning("UNSUPERVISED CONFIRMED classroom=%s incident=%s", self.classroom_id, result.incident_id)
            await self.event_bus.publish(
                Event(EventType.UNSUPERVISED_DETECTED, {**base_payload, "incident_id": result.incident_id})
            )

        if result.just_resolved:
            # AlertManager is the sole publisher of the outward, DB-enriched
            # ALERT_RESOLVED event — this is the raw supervision-layer signal
            # that tells it an alert (if one exists for this incident) should
            # now be resolved.
            await self.event_bus.publish(
                Event(
                    EventType.SUPERVISION_RESTORED,
                    {**base_payload, "incident_id": result.incident_id, "reason": result.resolution_reason},
                )
            )

        if result.state != self._previous_state:
            self._previous_state = result.state
            await self.event_bus.publish(Event(EventType.CLASSROOM_STATUS_CHANGED, base_payload))

        return result

    async def mark_camera_offline(self, timestamp: float) -> None:
        if self.camera_online:
            self.camera_online = False
            logger.warning("Camera %s offline", self.camera_id)
            await self.event_bus.publish(
                Event(EventType.CAMERA_OFFLINE, {"camera_id": self.camera_id, "classroom_id": self.classroom_id, "timestamp": timestamp})
            )

    async def mark_camera_online(self, timestamp: float) -> None:
        if not self.camera_online:
            self.camera_online = True
            logger.info("Camera %s back online", self.camera_id)
            await self.event_bus.publish(
                Event(EventType.CAMERA_ONLINE, {"camera_id": self.camera_id, "classroom_id": self.classroom_id, "timestamp": timestamp})
            )

    def is_stale(self, now: float | None = None) -> bool:
        """True if no frame has arrived within the offline timeout — the
        camera worker uses this to decide when to call mark_camera_offline."""
        if self.last_frame_at is None:
            return False
        now = now if now is not None else time.time()
        return (now - self.last_frame_at) > self.camera_offline_timeout_seconds
