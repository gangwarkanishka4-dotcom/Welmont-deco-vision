"""Generic HTTP-controlled relay (any relay board that exposes a simple
on/off HTTP endpoint). Retries with backoff and a hard timeout so a flaky
relay never blocks the alert pipeline."""
from __future__ import annotations

import asyncio
import logging

import httpx

from app.hardware.base import AlertOutput

logger = logging.getLogger(__name__)


class NetworkRelay(AlertOutput):
    def __init__(
        self,
        base_url: str,
        timeout_seconds: float = 2.0,
        max_retries: int = 3,
        trigger_path: str = "/relay/on",
        clear_path: str = "/relay/off",
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries
        self.trigger_path = trigger_path
        self.clear_path = clear_path

    async def trigger(self, alert_id: str, camera_id: str) -> bool:
        return await self._call(self.trigger_path, alert_id, camera_id, action="TRIGGER")

    async def clear(self, alert_id: str, camera_id: str) -> bool:
        return await self._call(self.clear_path, alert_id, camera_id, action="CLEAR")

    async def _call(self, path: str, alert_id: str, camera_id: str, action: str) -> bool:
        url = f"{self.base_url}{path}"
        last_error: Exception | None = None

        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            for attempt in range(1, self.max_retries + 1):
                try:
                    response = await client.post(url, json={"alert_id": alert_id, "camera_id": camera_id})
                    response.raise_for_status()
                    logger.info("[RELAY] %s ok alert=%s camera=%s attempt=%d", action, alert_id, camera_id, attempt)
                    return True
                except Exception as exc:  # noqa: BLE001 — network relay, any failure mode should retry/log
                    last_error = exc
                    logger.warning("[RELAY] %s failed attempt=%d/%d: %s", action, attempt, self.max_retries, exc)
                    if attempt < self.max_retries:
                        await asyncio.sleep(min(2 ** attempt * 0.2, 2.0))

        logger.error("[RELAY] %s FAILED after %d attempts alert=%s: %s", action, self.max_retries, alert_id, last_error)
        return False
