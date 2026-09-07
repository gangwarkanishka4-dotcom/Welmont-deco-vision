"""ESP32 relay driver. An ESP32 running the sketch described in the README
("How to connect ESP32/relay") exposes two GET endpoints, /buzzer/on and
/buzzer/off, each toggling a GPIO pin wired to a relay module. This is a thin
specialization of NetworkRelay with ESP32-appropriate defaults (GET instead
of POST, since most minimal ESP32 HTTP server sketches route GET handlers)."""
from __future__ import annotations

import asyncio
import logging

import httpx

from app.hardware.base import AlertOutput

logger = logging.getLogger(__name__)


class ESP32Relay(AlertOutput):
    def __init__(self, base_url: str, timeout_seconds: float = 2.0, max_retries: int = 3) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries

    async def trigger(self, alert_id: str, camera_id: str) -> bool:
        return await self._call("/buzzer/on", alert_id, camera_id, "TRIGGER")

    async def clear(self, alert_id: str, camera_id: str) -> bool:
        return await self._call("/buzzer/off", alert_id, camera_id, "CLEAR")

    async def _call(self, path: str, alert_id: str, camera_id: str, action: str) -> bool:
        url = f"{self.base_url}{path}"
        last_error: Exception | None = None

        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            for attempt in range(1, self.max_retries + 1):
                try:
                    response = await client.get(url)
                    response.raise_for_status()
                    logger.info("[ESP32] %s ok alert=%s camera=%s attempt=%d", action, alert_id, camera_id, attempt)
                    return True
                except Exception as exc:  # noqa: BLE001
                    last_error = exc
                    logger.warning("[ESP32] %s failed attempt=%d/%d: %s", action, attempt, self.max_retries, exc)
                    if attempt < self.max_retries:
                        await asyncio.sleep(min(2 ** attempt * 0.2, 2.0))

        logger.error("[ESP32] %s FAILED after %d attempts alert=%s: %s", action, self.max_retries, alert_id, last_error)
        return False
