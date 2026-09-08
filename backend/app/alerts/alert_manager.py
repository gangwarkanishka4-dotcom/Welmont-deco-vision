"""AlertManager owns the ONE authoritative mapping from incident_id -> Alert
row (spec §29 dedup): it is the only code that writes to the alerts table,
and the only publisher of the outward ALERT_CREATED / ALERT_RESOLVED /
ALERT_ACKNOWLEDGED events that the WebSocket layer and hardware layer react to.

It subscribes to the *domain* signals coming out of ClassroomMonitor
(UNSUPERVISED_DETECTED, SUPERVISION_RESTORED) rather than being called
directly, so the CV/supervision layer never needs to know a database or a
buzzer exists.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Awaitable, Callable, Protocol

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.config import Settings
from app.events.event_bus import Event, EventBus
from app.events.event_types import EventType
from app.hardware.base import AlertOutput
from app.models.alert import Alert
from app.models.alert_event import AlertEvent
from app.models.enums import AlertStatus

logger = logging.getLogger(__name__)


class MediaProvider(Protocol):
    """Injected by the camera worker layer so AlertManager never touches
    OpenCV directly. Best-effort — a failure here must never block alert
    creation/resolution. Incident evidence is a video clip only (spec §13) —
    there is deliberately no snapshot-capture method."""

    async def request_incident_clip(self, camera_id: str, alert_id: str) -> None: ...


@dataclass
class AlertManager:
    event_bus: EventBus
    session_factory: async_sessionmaker
    alert_output: AlertOutput
    settings: Settings
    media_provider: MediaProvider | None = None

    def register(self) -> None:
        self.event_bus.subscribe(EventType.UNSUPERVISED_DETECTED, self._on_unsupervised_detected)
        self.event_bus.subscribe(EventType.SUPERVISION_RESTORED, self._on_supervision_restored)

    async def acknowledge(self, alert_id: str) -> Alert | None:
        async with self.session_factory() as session:
            alert = await session.get(Alert, alert_id)
            if alert is None or alert.status != AlertStatus.ACTIVE.value:
                return alert
            alert.status = AlertStatus.ACKNOWLEDGED.value
            alert.acknowledged_at = datetime.now(timezone.utc)
            session.add(AlertEvent(alert_id=alert.alert_id, event_type="ACKNOWLEDGED", message=""))
            await session.commit()
            await session.refresh(alert)

        await self.event_bus.publish(Event(EventType.ALERT_ACKNOWLEDGED, {"alert_id": alert_id}))
        return alert

    async def resolve_manually(self, alert_id: str) -> Alert | None:
        return await self._resolve(alert_id, reason="manual")

    async def _on_unsupervised_detected(self, event: Event) -> None:
        payload = event.payload
        incident_id = payload["incident_id"]

        async with self.session_factory() as session:
            existing = await session.scalar(select(Alert).where(Alert.incident_id == incident_id))
            if existing is not None:
                # Deduplication: this incident already has an alert row —
                # a duplicate UNSUPERVISED_DETECTED must never create a
                # second alert (spec §29).
                return

            confirmed_at = datetime.now(timezone.utc)
            started_at = confirmed_at - timedelta(seconds=self.settings.unsupervised_delay_seconds)
            alert = Alert(
                incident_id=incident_id,
                camera_id=payload["camera_id"],
                classroom_id=payload["classroom_id"],
                started_at=started_at,
                confirmed_at=confirmed_at,
                status=AlertStatus.ACTIVE.value,
                children_count=payload["children_count"],
                adult_count=payload["adult_count"],
            )
            session.add(alert)
            await session.flush()
            session.add(AlertEvent(alert_id=alert.alert_id, event_type="CREATED", message="Unsupervised classroom confirmed"))
            await session.commit()
            await session.refresh(alert)

        logger.warning("Alert %s created for incident %s", alert.alert_id, incident_id)

        buzzer_ok = await self.alert_output.trigger(alert.alert_id, alert.camera_id)
        await self._log_alert_event(alert.alert_id, "BUZZER_TRIGGERED", "" if buzzer_ok else "buzzer trigger failed")
        if buzzer_ok:
            await self.event_bus.publish(Event(EventType.BUZZER_TRIGGERED, {"alert_id": alert.alert_id, "camera_id": alert.camera_id}))

        await self.event_bus.publish(Event(EventType.ALERT_CREATED, _alert_payload(alert)))

        if self.media_provider is not None:
            try:
                await self.media_provider.request_incident_clip(alert.camera_id, alert.alert_id)
            except Exception:
                logger.exception("Incident clip capture failed for alert %s (non-fatal)", alert.alert_id)

    async def _on_supervision_restored(self, event: Event) -> None:
        incident_id = event.payload["incident_id"]
        reason = event.payload.get("reason", "adult_returned")

        async with self.session_factory() as session:
            alert = await session.scalar(select(Alert).where(Alert.incident_id == incident_id))
            if alert is None or alert.status == AlertStatus.RESOLVED.value:
                return
            alert_id = alert.alert_id
            camera_id = alert.camera_id

        await self._resolve(alert_id, reason=reason, camera_id=camera_id)

    async def _resolve(self, alert_id: str, reason: str, camera_id: str | None = None) -> Alert | None:
        async with self.session_factory() as session:
            alert = await session.get(Alert, alert_id)
            if alert is None or alert.status == AlertStatus.RESOLVED.value:
                return alert
            alert.status = AlertStatus.RESOLVED.value
            alert.resolved_at = datetime.now(timezone.utc)
            camera_id = camera_id or alert.camera_id
            session.add(AlertEvent(alert_id=alert_id, event_type="RESOLVED", message=reason))
            await session.commit()
            await session.refresh(alert)

        buzzer_ok = await self.alert_output.clear(alert_id, camera_id)
        await self._log_alert_event(alert_id, "BUZZER_CLEARED", "" if buzzer_ok else "buzzer clear failed")
        if buzzer_ok:
            await self.event_bus.publish(Event(EventType.BUZZER_CLEARED, {"alert_id": alert_id, "camera_id": camera_id}))

        await self.event_bus.publish(Event(EventType.ALERT_RESOLVED, _alert_payload(alert)))
        logger.info("Alert %s resolved (%s)", alert_id, reason)
        return alert

    async def _log_alert_event(self, alert_id: str, event_type: str, message: str) -> None:
        async with self.session_factory() as session:
            session.add(AlertEvent(alert_id=alert_id, event_type=event_type, message=message))
            await session.commit()


def _alert_payload(alert: Alert) -> dict:
    return {
        "alert_id": alert.alert_id,
        "incident_id": alert.incident_id,
        "camera_id": alert.camera_id,
        "classroom_id": alert.classroom_id,
        "type": alert.type,
        "severity": alert.severity,
        "status": alert.status,
        "started_at": alert.started_at.isoformat(),
        "confirmed_at": alert.confirmed_at.isoformat(),
        "resolved_at": alert.resolved_at.isoformat() if alert.resolved_at else None,
        "children_count": alert.children_count,
        "adult_count": alert.adult_count,
        "clip_url": alert.clip_url,
    }
