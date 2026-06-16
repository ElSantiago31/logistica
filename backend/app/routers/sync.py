"""Sync router — offline data download + attendance batch upload."""
import logging
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

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/sync", tags=["Sync"])


def _to_uuid(val):
    """Convert string to UUID, return None if invalid/empty."""
    if val is None or val == "":
        return None
    if isinstance(val, uuid.UUID):
        return val
    try:
        return uuid.UUID(str(val))
    except (ValueError, AttributeError):
        return None


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

    from app.models.roles import Role

    # Get assignments with operator info + role
    result = await db.execute(
        select(EventAssignment, Operator, User, Role)
        .join(Operator, Operator.id == EventAssignment.operator_id)
        .join(User, User.id == Operator.user_id)
        .outerjoin(Role, Role.id == EventAssignment.role_id)
        .where(EventAssignment.event_id == event_id)
    )
    rows = result.all()

    assignments = []
    for assignment, operator, op_user, role in rows:
        assignments.append({
            "id": str(assignment.id),
            "operator_id": str(operator.id),
            "full_name": f"{op_user.first_name} {op_user.last_name}",
            "document_number": op_user.document_number or "",
            "role_name": role.name if role else "Operador",
            "status": assignment.status,
            "photo_url": operator.photo_thumbnail_path,
            "shirt_number": assignment.shirt_number,
            "jacket_number": assignment.jacket_number,
            "cap_number": assignment.cap_number,
        })

    # Log sync session (non-critical)
    try:
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
    except Exception:
        await db.rollback()

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


async def _check_uniform_conflicts(
    db: AsyncSession,
    event_id: uuid.UUID,
    exclude_assignment_id,
    shirt,
    jacket,
    cap,
):
    """Verifica si shirt/jacket/cap ya están asignados a otro operador en el evento.
    Retorna mensaje de conflicto (str) o None si todo OK."""
    if not any([shirt, jacket, cap]):
        return None

    result = await db.execute(
        select(EventAssignment, Operator, User)
        .join(Operator, Operator.id == EventAssignment.operator_id)
        .join(User, User.id == Operator.user_id)
        .where(EventAssignment.event_id == event_id)
    )
    rows = result.all()
    for assignment, operator, user in rows:
        if exclude_assignment_id and str(assignment.id) == str(exclude_assignment_id):
            continue
        name = f"{user.first_name} {user.last_name}"
        if shirt and assignment.shirt_number and str(assignment.shirt_number).strip() == str(shirt).strip():
            return f"La camisa #{shirt} ya está asignada a {name}"
        if jacket and assignment.jacket_number and str(assignment.jacket_number).strip() == str(jacket).strip():
            return f"La chaqueta #{jacket} ya está asignada a {name}"
        if cap and assignment.cap_number and str(assignment.cap_number).strip() == str(cap).strip():
            return f"La gorra #{cap} ya está asignada a {name}"
    return None


def _parse_datetime(val):
    """Convert ISO string or timestamp to datetime for DB."""
    if val is None or val == "":
        return datetime.utcnow()
    if isinstance(val, datetime):
        return val
    try:
        # Handle ISO 8601 (e.g. "2026-06-13T20:00:00.000Z")
        return datetime.fromisoformat(str(val).replace("Z", "+00:00"))
    except (ValueError, TypeError):
        try:
            return datetime.fromisoformat(str(val))
        except (ValueError, TypeError):
            return datetime.utcnow()


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

    session_event_id = _to_uuid(records[0].get("event_id"))
    if not session_event_id:
        raise HTTPException(400, "event_id inválido o vacío en records[0]")

    synced = 0
    failed = 0
    sync_session = None

    # Crear SyncSession en su propia transacción (savepoint)
    try:
        async with db.begin_nested():
            sync_session = SyncSession(
                event_id=session_event_id,
                synced_by=user.id,
                session_type="upload",
                status="in_progress",
                records_total=len(records),
                records_synced=0,
                started_at=datetime.utcnow(),
            )
            db.add(sync_session)
            await db.flush()
    except Exception as exc:
        await db.rollback()
        logger.error("Error creando sync_session: %s", exc)
        raise HTTPException(500, f"Error en sync session: {exc}")

    # Procesar cada record en su propio savepoint
    for idx, rec in enumerate(records):
        try:
            operator_id = _to_uuid(rec.get("operator_id"))
            event_id = _to_uuid(rec.get("event_id"))
            assignment_id = _to_uuid(rec.get("assignment_id"))

            if not operator_id or not event_id:
                logger.warning("Record #%d sin IDs válidos: %s", idx, rec)
                failed += 1
                continue

            check_in_time = _parse_datetime(rec.get("check_in_time"))

            async with db.begin_nested():
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
                    assignment_id=assignment_id,
                    check_in_time=check_in_time,
                    check_in_method=str(rec.get("check_in_method", "qr"))[:20],
                    scanned_code=rec.get("scanned_code"),
                    verified_by=user.id,
                    sync_session_id=sync_session.id,
                    is_offline=True,
                    device_id=str(rec.get("device_id") or "")[:100] or None,
                )
                db.add(log)

                # Update assignment status to checked_in + uniform
                if assignment_id:
                    assignment = await db.get(EventAssignment, assignment_id)
                    if assignment:
                        assignment.status = "checked_in"
                        shirt = rec.get("shirt_number")
                        jacket = rec.get("jacket_number")
                        cap = rec.get("cap_number")
                        if shirt:
                            assignment.shirt_number = str(shirt)
                        if jacket:
                            assignment.jacket_number = str(jacket)
                        if cap:
                            assignment.cap_number = str(cap)

                synced += 1
        except Exception as exc:
            logger.error("Error procesando record #%d: %s — %s", idx, exc, rec)
            failed += 1

    # Actualizar sync_session
    try:
        sync_session.records_synced = synced
        sync_session.status = "completed" if failed == 0 else "partial"
        sync_session.completed_at = datetime.utcnow()
        await db.commit()
    except Exception as exc:
        await db.rollback()
        logger.error("Error al finalizar sync_session: %s", exc)
        # Los datos ya están commiteados vía savepoints, solo falló la metadata
        logger.warning("Attendance synced=%d failed=%d (metadata no guardada)", synced, failed)

    return {
        "synced": synced,
        "failed": failed,
        "total": len(records),
        "sync_session_id": str(sync_session.id) if sync_session else None,
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

    operator_id = _to_uuid(payload.get("operator_id"))
    assignment_id = _to_uuid(payload.get("assignment_id"))
    method = payload.get("method", "manual")
    code = payload.get("scanned_code")
    # Optional uniform fields
    shirt_number = payload.get("shirt_number")
    jacket_number = payload.get("jacket_number")
    cap_number = payload.get("cap_number")

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

    # Validar conflictos de uniform ANTES de guardar
    conflict = await _check_uniform_conflicts(
        db, event_id, assignment_id, shirt_number, jacket_number, cap_number
    )
    if conflict:
        raise HTTPException(409, conflict)

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

    # Update assignment status to checked_in + save uniform
    if assignment_id:
        assignment = await db.get(EventAssignment, assignment_id)
        if assignment:
            assignment.status = "checked_in"
            if shirt_number is not None:
                assignment.shirt_number = shirt_number or None
            if jacket_number is not None:
                assignment.jacket_number = jacket_number or None
            if cap_number is not None:
                assignment.cap_number = cap_number or None

    try:
        await db.commit()
    except Exception as exc:
        await db.rollback()
        logger.error("Error en check-in: %s", exc)
        raise HTTPException(500, f"Error al guardar check-in: {exc}")

    return {"status": "checked_in", "log_id": str(log.id)}


@router.patch("/assignments/{assignment_id}/uniform")
async def update_uniform(
    assignment_id: uuid.UUID,
    payload: dict,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """Edita la indumentaria asignada a un operador (incluso después del check-in)."""
    if user.user_type not in ("admin", "superadmin", "coordinator"):
        raise HTTPException(403, "Sin permisos")

    assignment = await db.get(EventAssignment, assignment_id)
    if not assignment:
        raise HTTPException(404, "Asignación no encontrada")

    shirt_number = payload.get("shirt_number") if "shirt_number" in payload else assignment.shirt_number
    jacket_number = payload.get("jacket_number") if "jacket_number" in payload else assignment.jacket_number
    cap_number = payload.get("cap_number") if "cap_number" in payload else assignment.cap_number

    # Validar conflictos de uniform (excluyendo la asignación actual)
    conflict = await _check_uniform_conflicts(
        db, assignment.event_id, assignment_id, shirt_number, jacket_number, cap_number
    )
    if conflict:
        raise HTTPException(409, conflict)

    if "shirt_number" in payload:
        assignment.shirt_number = payload["shirt_number"] or None
    if "jacket_number" in payload:
        assignment.jacket_number = payload["jacket_number"] or None
    if "cap_number" in payload:
        assignment.cap_number = payload["cap_number"] or None

    await db.commit()

    return {
        "status": "updated",
        "assignment_id": str(assignment.id),
        "shirt_number": assignment.shirt_number,
        "jacket_number": assignment.jacket_number,
        "cap_number": assignment.cap_number,
    }