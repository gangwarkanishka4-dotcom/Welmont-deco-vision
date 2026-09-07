"""Hardware output interface. The alert engine only ever talks to this
contract — it has no idea whether the buzzer is a mock, a network relay, or
an ESP32; swapping the driver is a one-line config change (ALERT_OUTPUT_DRIVER)."""
from __future__ import annotations

from abc import ABC, abstractmethod


class AlertOutput(ABC):
    @abstractmethod
    async def trigger(self, alert_id: str, camera_id: str) -> bool:
        """Activate the physical buzzer/relay for this alert. Returns True on
        confirmed success."""
        ...

    @abstractmethod
    async def clear(self, alert_id: str, camera_id: str) -> bool:
        """Deactivate the buzzer/relay once the alert resolves."""
        ...
