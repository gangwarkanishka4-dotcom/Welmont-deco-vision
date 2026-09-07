from __future__ import annotations

from app.config import Settings
from app.hardware.base import AlertOutput
from app.hardware.esp32_relay import ESP32Relay
from app.hardware.mock_buzzer import MockBuzzer
from app.hardware.network_relay import NetworkRelay


def build_alert_output(settings: Settings) -> AlertOutput:
    driver = settings.alert_output_driver.lower()
    if driver == "mock":
        return MockBuzzer()
    if driver == "network_relay":
        return NetworkRelay(settings.relay_base_url, settings.relay_timeout_seconds, settings.relay_max_retries)
    if driver == "esp32":
        return ESP32Relay(settings.relay_base_url, settings.relay_timeout_seconds, settings.relay_max_retries)
    raise ValueError(f"Unknown ALERT_OUTPUT_DRIVER: {settings.alert_output_driver}")
