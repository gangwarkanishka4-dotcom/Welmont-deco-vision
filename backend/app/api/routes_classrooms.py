from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.alert import Alert
from app.models.camera import Camera
from app.models.classroom import Classroom
from app.models.enums import AlertStatus
from app.schemas.alert import ClassroomStatusOut
from app.schemas.classroom import ClassroomCreate, ClassroomOut

router = APIRouter(prefix="/api/classrooms", tags=["classrooms"])


@router.get("", response_model=list[ClassroomOut])
async def list_classrooms(db: AsyncSession = Depends(get_db)) -> list[Classroom]:
    return list((await db.scalars(select(Classroom))).all())


@router.post("", response_model=ClassroomOut, status_code=201)
async def create_classroom(payload: ClassroomCreate, db: AsyncSession = Depends(get_db)) -> Classroom:
    classroom = Classroom(name=payload.name, location=payload.location)
    db.add(classroom)
    await db.commit()
    await db.refresh(classroom)
    return classroom


@router.get("/{classroom_id}/status", response_model=list[ClassroomStatusOut])
async def classroom_status(classroom_id: str, request: Request, db: AsyncSession = Depends(get_db)) -> list[ClassroomStatusOut]:
    classroom = await db.get(Classroom, classroom_id)
    if classroom is None:
        raise HTTPException(404, "Classroom not found")

    cameras = list((await db.scalars(select(Camera).where(Camera.classroom_id == classroom_id))).all())
    registry = request.app.state.registry
    results: list[ClassroomStatusOut] = []

    for camera in cameras:
        worker = registry.get(camera.id)
        active_alert = await db.scalar(
            select(Alert).where(Alert.classroom_id == classroom_id, Alert.status != AlertStatus.RESOLVED.value)
        )
        results.append(
            ClassroomStatusOut(
                classroom_id=classroom_id,
                classroom_name=classroom.name,
                camera_id=camera.id,
                camera_status="ONLINE" if (worker and worker.monitor.camera_online) else "OFFLINE",
                supervision_status=worker.monitor.state_machine.state.value if worker else "UNKNOWN",
                adult_count=worker.state.adult_count if worker else 0,
                child_count=worker.state.child_count if worker else 0,
                unknown_count=worker.state.unknown_count if worker else 0,
                active_alert_id=active_alert.alert_id if active_alert else None,
            )
        )

    return results
