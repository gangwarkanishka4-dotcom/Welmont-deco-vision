from __future__ import annotations

from fastapi import Request

from app.alerts.alert_manager import AlertManager


def get_alert_manager(request: Request) -> AlertManager:
    return request.app.state.alert_manager
