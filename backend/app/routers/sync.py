"""Sync router — offline data download + attendance batch upload."""
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies.auth import get_current_user
from app.models.events import Event, EventAssignment, EventStaffNeed
from app.models.operators import Operator
from app.models.sync import SyncSession, AttendanceLog
from app.models.users import User

router = APIRouter(prefix="/api/sync", tags=["Sync"])


@router.get("/events/{event_id}/offline-data")
async def get_offline_data(
    event_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """Download event data for offline PWA use."""
    if user.user_type not in ("admin", "superadmin", "coordinator"):
        raise HTTPException(403, "Sin permisos")

    event = await db.get(Event, event_id)
    if not event:
        raise HTTPException(404, "Evento no encontrado")

    # Get assignments with operator info
    result = await db.execute(
        select(EventAssignment, Operator, User)
        .join(Operator, Operator.id == EventAssignment.operator_id)
        .join(User, User.id == Operator.user_id)
        .where(EventAssignment.event_id == event_id)
    )
    rows = result.all()

    assignments = []
    for assignment, operator, op_user in rows:
        assignments.append({
            "id": str(assignment.id),
            "operator_id": str(operator.id),
            "full_name": f"{op_user.first_name} {op_user.last_name}",
            "document_number": op_user.document_number or "",
            "role_name": assignment.role_name or "Operador",
            "status": assignment.status,
            "photo_url": operator.photo_url,
        })

    # Log sync session
    sync_session = SyncSession(
        event_id=event_id,
        synced_by=user.id,
        session_type="download",
        status="completed",
        records_total=len(assignments),
        records_synced=len(assignments),
        started_at=datetime.utcnow(),
        completed_at=datetime.utcnow(),
    )
    db.add(sync_session)
    await db.commit()

    return {
        "id": str(event.id),
        "name": event.name,
        "status": event.status,
        "start_date": str(event.start_date) if event.start_date else None,
        "end_date": str(event.end_date) if event.end_date else None,
        "location": event.location,
        "description": event.description,
        "assignments": assignments,
    }


@router.post("/attendance")
async def sync_attendance(
    payload: dict,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """Batch upload attendance records from offline PWA."""
    if user.user_type not in ("admin", "superadmin", "coordinator"):
        raise HTTPException(403, "Sin permisos")

    records = payload.get("records", [])
    if not records:
        return {"synced": 0, "failed": 0, "total": 0}

    # Create sync session
    sync_session = SyncSession(
        event_id=records[0].get("event_id"),
        synced_by=user.id,
        session_type="upload",
        status="in_progress",
        records_total=len(records),
        records_synced=0,
        started_at=datetime.utcnow(),
    )
    db.add(sync_session)
    await db.flush()

    synced = 0
    failed = 0

    for rec in records:
        try:
            operator_id = rec.get("operator_id")
            event_id = rec.get("event_id")

            # Check for duplicate
            existing = await db.execute(
                select(AttendanceLog).where(
                    AttendanceLog.event_id == event_id,
                    AttendanceLog.operator_id == operator_id,
                )
            )
            if existing.scalar_one_or_none():
                failed += 1
                continue

            log = AttendanceLog(
                event_id=event_id,
                operator_id=operator_id,
                check_in_time=rec.get("check_in_time"),
                check_in_method=rec.get("check_in_method", "qr"),
                scanned_code=rec.get("scanned_code"),
                verified_by=user.id,
                sync_session_id=sync_session.id,
                is_offline=True,
                device_id=rec.get("device_id"),
            )
            db.add(log)
            synced += 1
        except Exception:
            failed += 1

    sync_session.records_synced = synced
    sync_session.status = "completed" if failed == 0 else "partial"
    sync_session.completed_at = datetime.utcnow()

    await db.commit()

    return {
        "synced": synced,
        "failed": failed,
        "total": len(records),
        "sync_session_id": str(sync_session.id),
    }


@router.get("/status")
async def sync_status(
    event_id: uuid.UUID = None,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """Get sync status for dashboard."""
    if user.user_type not in ("admin", "superadmin"):
        raise HTTPException(403, "Sin permisos")

    query = select(SyncSession)
    if event_id:
        query = query.where(SyncSession.event_id == event_id)

    result = await db.execute(
        query.order_by(SyncSession.created_at.desc()).limit(20)
    )
    sessions = result.scalars().all()

    return {
        "sessions": [
            {
                "id": str(s.id),
                "event_id": str(s.event_id),
                "type": s.session_type,
                "status": s.status,
                "records_total": s.records_total,
                "records_synced": s.records_synced,
                "started_at": str(s.started_at) if s.started_at else None,
                "completed_at": str(s.completed_at) if s.completed_at else None,
                "error_message": s.error_message,
            }
            for s in sessions
        ]
    }


@router.get("/events/{event_id}/attendance")
async def get_attendance(
    event_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """Get attendance records for an event."""
    if user.user_type not in ("admin", "superadmin", "coordinator"):
        raise HTTPException(403, "Sin permisos")

    result = await db.execute(
        select(AttendanceLog, Operator, User)
        .join(Operator, Operator.id == AttendanceLog.operator_id)
        .join(User, User.id == Operator.user_id)
        .where(AttendanceLog.event_id == event_id)
    )
    rows = result.all()

    return {
        "event_id": str(event_id),
        "records": [
            {
                "id": str(log.id),
                "operator_name": f"{u.first_name} {u.last_name}",
                "check_in_time": str(log.check_in_time) if log.check_in_time else None,
                "check_out_time": str(log.check_out_time) if log.check_out_time else None,
                "method": log.check_in_method,
                "is_offline": log.is_offline,
            }
            for log, op, u in rows
        ],
        "total": len(rows),
    }


@router.post("/events/{event_id}/check-in")
async def check_in(
    event_id: uuid.UUID,
    payload: dict,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """Single check-in (online) via QR scan or manual."""
    if user.user_type not in ("admin", "superadmin", "coordinator"):
        raise HTTPException(403, "Sin permisos")

    operator_id = payload.get("operator_id")
    assignment_id = payload.get("assignment_id")
    method = payload.get("method", "manual")
    code = payload.get("scanned_code")

    if not operator_id:
        raise HTTPException(400, "operator_id requerido")

    # Check duplicate
    existing = await db.execute(
        select(AttendanceLog).where(
            AttendanceLog.event_id == event_id,
            AttendanceLog.operator_id == operator_id,
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(409, "Operador ya registrado")

    log = AttendanceLog(
        event_id=event_id,
        operator_id=operator_id,
        assignment_id=assignment_id,
        check_in_time=datetime.utcnow(),
        check_in_method=method,
        scanned_code=code,
        verified_by=user.id,
        is_offline=False,
    )
    db.add(log)
    await db.commit()

    return {"status": "checked_in", "log_id": str(log.id)}