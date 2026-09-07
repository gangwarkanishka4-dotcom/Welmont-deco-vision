from __future__ import annotations

import logging

from app.hardware.base import AlertOutput

logger = logging.getLogger(__name__)


class MockBuzzer(AlertOutput):
    """Default driver — logs the trigger/clear so the whole pipeline is
    exercisable with no physical hardware attached. Tracks state in-memory
    so tests/UI can assert on it."""

    def __init__(self) -> None:
        self.active_alerts: set[str] = set()

    async def trigger(self, alert_id: str, camera_id: str) -> bool:
        self.active_alerts.add(alert_id)
        logger.info("[MOCK BUZZER] TRIGGER alert=%s camera=%s", alert_id, camera_id)
        return True

    async def clear(self, alert_id: str, camera_id: str) -> bool:
        self.active_alerts.discard(alert_id)
        logger.info("[MOCK BUZZER] CLEAR alert=%s camera=%s", alert_id, camera_id)
        return True
