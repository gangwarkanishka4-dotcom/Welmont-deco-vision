from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.alerts.alert_manager import AlertManager
from app.api.deps import get_alert_manager
from app.database import get_db
from app.models.alert import Alert
from app.models.alert_event import AlertEvent
from app.schemas.alert import AlertEventOut, AlertOut

router = APIRouter(prefix="/api/alerts", tags=["alerts"])


@router.get("", response_model=list[AlertOut])
async def list_alerts(
    status: str | None = None,
    classroom_id: str | None = None,
    limit: int = 100,
    db: AsyncSession = Depends(get_db),
) -> list[Alert]:
    query = select(Alert).order_by(Alert.created_at.desc()).limit(limit)
    if status:
        query = query.where(Alert.status == status)
    if classroom_id:
        query = query.where(Alert.classroom_id == classroom_id)
    return list((await db.scalars(query)).all())


@router.get("/{alert_id}", response_model=AlertOut)
async def get_alert(alert_id: str, db: AsyncSession = Depends(get_db)) -> Alert:
    alert = await db.get(Alert, alert_id)
    if alert is None:
        raise HTTPException(404, "Alert not found")
    return alert


@router.get("/{alert_id}/events", response_model=list[AlertEventOut])
async def get_alert_events(alert_id: str, db: AsyncSession = Depends(get_db)) -> list[AlertEvent]:
    return list((await db.scalars(select(AlertEvent).where(AlertEvent.alert_id == alert_id).order_by(AlertEvent.created_at))).all())


@router.post("/{alert_id}/acknowledge", response_model=AlertOut)
async def acknowledge_alert(alert_id: str, manager: AlertManager = Depends(get_alert_manager)) -> Alert:
    alert = await manager.acknowledge(alert_id)
    if alert is None:
        raise HTTPException(404, "Alert not found")
    return alert


@router.post("/{alert_id}/resolve", response_model=AlertOut)
async def resolve_alert(alert_id: str, manager: AlertManager = Depends(get_alert_manager)) -> Alert:
    """Manual override — the system already auto-resolves when the adult
    returns; this exists for an operator to close out an incident by hand
    (e.g. after reviewing the clip and confirming it's handled)."""
    alert = await manager.resolve_manually(alert_id)
    if alert is None:
        raise HTTPException(404, "Alert not found")
    return alert
