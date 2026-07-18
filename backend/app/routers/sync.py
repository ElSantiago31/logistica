"""Sync router — offline data download + attendance batch upload."""
import logging
import time
import uuid
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import safe_http_error
from app.database import get_db
from app.dependencies.auth import get_current_user
from app.models.events import Event, EventAssignment, EventStaffNeed, EventCoordinatorQuota
from app.models.operators import Operator
from app.models.sync import SyncSession, AttendanceLog
from app.models.users import User
from app.websockets.manager import manager as ws_manager

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/sync", tags=["Sync"])

# --- Presence tracking (Fase 3) ---
# {event_id_str: {device_id: last_seen_epoch}}
# In-memory, single-process. Para producción multi-worker usar Redis/pub-sub.
_checkin_presence: dict = {}
PRESENCE_TTL_SECONDS = 15


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


async def _resolve_staff_access(
    db: AsyncSession,
    user: User,
    event_id,
    allow_checkin: bool = True,
):
    """Valida permisos de staff para un evento.

    Roles base (admin/superadmin/coordinator y, segun flag, checkin)
    siempre tienen acceso. Los operadores deben tener un EventStaffAssignment
    activo en el evento con el staff_role correspondiente.

    Returns:
        staff_role (str|None): el staff_role del operador, o None si es rol base.
    Raises:
        HTTPException(403) si no tiene permisos.
    """
    base_roles = {"admin", "superadmin", "coordinator"}
    if allow_checkin:
        base_roles.add("checkin")

    if user.user_type in base_roles:
        return None

    if user.user_type == "operator" and event_id:
        from app.models.events import EventStaffAssignment
        allowed = set()
        if allow_checkin:
            allowed.add("checkin")
        result = await db.execute(
            select(EventStaffAssignment.staff_role).where(
                EventStaffAssignment.event_id == event_id,
                EventStaffAssignment.user_id == user.id,
                EventStaffAssignment.staff_role.in_(allowed),
                EventStaffAssignment.is_active == True,
            )
        )
        role = result.scalar_one_or_none()
        if role:
            return role

    raise HTTPException(403, "Sin permisos")


def _can_manage_uniform(user: User, staff_role: Optional[str] = None) -> bool:
    """Determina si el usuario puede setear indumentaria.

    Pueden: admin, superadmin, coordinator, checkin (rol base), u operador
    cuyo staff_role en el evento sea 'checkin'.
    """
    if user.user_type in ("admin", "superadmin", "coordinator", "checkin"):
        return True
    if user.user_type == "operator" and staff_role == "checkin":
        return True
    return False


@router.get("/events/{event_id}/offline-data")
async def get_offline_data(
    event_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """Download event data for offline PWA use."""
    staff_role = await _resolve_staff_access(db, user, event_id)
    can_manage_uniform = _can_manage_uniform(user, staff_role)

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

    # --- Mapa de coordinadores (Opción A: por área del rol) ---
    area_to_coord, general_coord = await _build_coordinator_map(db, event_id)

    assignments = []
    for assignment, operator, op_user, role in rows:
        # Determinar coordinador del operador según su área
        coord_name, coord_role = general_coord if general_coord else ("Sin asignar", "")
        if role and role.area and role.area in area_to_coord:
            coord_name, coord_role = area_to_coord[role.area]

        # Si el operador tiene programmed_by (del formulario de registro),
        # ese coordinador tiene PRIORIDAD sobre el inferido por área.
        programmed_by = getattr(assignment, "programmed_by", None)
        if programmed_by:
            coord_name = programmed_by
            coord_role = "Programado por"

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
            "coordinator_name": coord_name,
            "coordinator_role_name": coord_role,
            "admitted_by": assignment.admitted_by,
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

    # --- Cupos por coordinador (para tarjetas) ---
    quotas = await _get_coordinator_quotas(db, event_id)

    return {
        "id": str(event.id),
        "name": event.name,
        "status": event.status,
        "start_date": str(event.start_date) if event.start_date else None,
        "end_date": str(event.end_date) if event.end_date else None,
        "location": event.location,
        "description": event.description,
        "assignments": assignments,
        "coordinator_quotas": quotas,
        "staff_role": staff_role,
        "can_manage_uniform": can_manage_uniform,
    }


async def _get_coordinator_quotas(db: AsyncSession, event_id: uuid.UUID):
    """Retorna cupos por coordinador con conteo en vivo.

    Estructura por coordinador:
      coordinator: nombre en MAYÚSCULAS
      quota: cupo máximo
      checked_in: cuántos ya hicieron check-in (admitted_by)
      programmed: cuántos programó en total (programmed_by)
      available: quota - checked_in
      full: bool (available <= 0)
    """
    # Cupos configurados
    result = await db.execute(
        select(EventCoordinatorQuota)
        .where(EventCoordinatorQuota.event_id == event_id)
        .order_by(EventCoordinatorQuota.coordinator)
    )
    quotas = result.scalars().all()

    # Conteo en vivo (checked_in por admitted_by)
    counts_result = await db.execute(
        select(
            EventAssignment.admitted_by,
            func.count(EventAssignment.id).label("cnt"),
        )
        .where(
            EventAssignment.event_id == event_id,
            EventAssignment.status == "checked_in",
            EventAssignment.admitted_by.isnot(None),
        )
        .group_by(EventAssignment.admitted_by)
    )
    checked_in_counts = {row.admitted_by: row.cnt for row in counts_result.all()}

    # Conteo programmed (todos los que programó, sin importar check-in)
    prog_result = await db.execute(
        select(
            EventAssignment.programmed_by,
            func.count(EventAssignment.id).label("cnt"),
        )
        .where(
            EventAssignment.event_id == event_id,
            EventAssignment.programmed_by.isnot(None),
        )
        .group_by(EventAssignment.programmed_by)
    )
    programmed_counts = {row.programmed_by: row.cnt for row in prog_result.all()}

    # --- Conteo de cesiones: operadores checked_in cuyo admitted_by !=
    # programmed_by (fueron cedidos por otro coordinador). ---
    # Estructura: {admitted_by: {programmed_by_original: count}}
    ceded_result = await db.execute(
        select(
            EventAssignment.admitted_by,
            EventAssignment.programmed_by,
            func.count(EventAssignment.id).label("cnt"),
        )
        .where(
            EventAssignment.event_id == event_id,
            EventAssignment.status == "checked_in",
            EventAssignment.admitted_by.isnot(None),
            EventAssignment.programmed_by.isnot(None),
            func.upper(EventAssignment.admitted_by) != func.upper(EventAssignment.programmed_by),
        )
        .group_by(EventAssignment.admitted_by, EventAssignment.programmed_by)
    )
    ceded_map: dict[str, dict[str, int]] = {}
    for row in ceded_result.all():
        admitted = (row.admitted_by or "").strip().upper()
        programmed = (row.programmed_by or "").strip().upper()
        if not admitted or not programmed:
            continue
        ceded_map.setdefault(admitted, {})
        ceded_map[admitted][programmed] = ceded_map[admitted].get(programmed, 0) + int(row.cnt)

    out = []
    for q in quotas:
        ci = checked_in_counts.get(q.coordinator, 0)
        pg = programmed_counts.get(q.coordinator, 0)
        coord_key = (q.coordinator or "").strip().upper()
        ceded_by = ceded_map.get(coord_key, {})
        ceded_total = sum(ceded_by.values())
        out.append({
            "coordinator": q.coordinator,
            "quota": q.quota,
            "checked_in": ci,
            "programmed": pg,
            "available": q.quota - ci,
            "full": ci >= q.quota,
            "ceded_by": ceded_by,        # {coordinador_origen: n}
            "ceded_total": ceded_total,  # total cedidos recibidos
        })
    return out


async def _check_coordinator_quota(db: AsyncSession, event_id: uuid.UUID, coordinator: str):
    """Verifica si un coordinador tiene cupo disponible.

    Returns:
        (ok: bool, message: str, quota_info: dict|None)
    """
    if not coordinator:
        return True, "", None
    # Normalizar a MAYÚSCULAS para comparación
    coord = coordinator.strip().upper()
    result = await db.execute(
        select(EventCoordinatorQuota)
        .where(
            EventCoordinatorQuota.event_id == event_id,
            func.upper(EventCoordinatorQuota.coordinator) == coord,
        )
    )
    quota_row = result.scalar_one_or_none()
    if not quota_row:
        # No hay cupo configurado: no aplicar restricción
        return True, "", None

    count_result = await db.execute(
        select(func.count(EventAssignment.id))
        .where(
            EventAssignment.event_id == event_id,
            EventAssignment.status == "checked_in",
            func.upper(EventAssignment.admitted_by) == coord,
        )
    )
    checked_in = count_result.scalar() or 0
    available = quota_row.quota - checked_in
    if available <= 0:
        return False, f"Cupo lleno para {quota_row.coordinator} ({checked_in}/{quota_row.quota})", {
            "coordinator": quota_row.coordinator,
            "quota": quota_row.quota,
            "checked_in": checked_in,
            "available": available,
        }
    return True, "", {
        "coordinator": quota_row.coordinator,
        "quota": quota_row.quota,
        "checked_in": checked_in,
        "available": available,
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
    records = payload.get("records", [])
    if not records:
        return {"synced": 0, "failed": 0, "total": 0}

    session_event_id = _to_uuid(records[0].get("event_id"))
    if not session_event_id:
        raise HTTPException(400, "event_id inválido o vacío en records[0]")

    staff_role = await _resolve_staff_access(db, user, session_event_id)
    # Rol checkin u operador-checkin no puede setear indumentaria en sync batch
    can_set_uniform_batch = _can_manage_uniform(user, staff_role)

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
        safe_http_error(
            status_code=500,
            client_message="Error interno del servidor",
            log_detail="Error creando sync_session",
            exc=exc,
        )

    # Procesar cada record en su propio savepoint
    for idx, rec in enumerate(records):
        try:
            operator_id = _to_uuid(rec.get("operator_id"))
            event_id = _to_uuid(rec.get("event_id"))
            assignment_id = _to_uuid(rec.get("assignment_id"))

            if not operator_id or not event_id:
                logger.warning("Record #%d sin IDs válidos (operator_id/event_id faltantes)", idx)
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
                    check_in_method=str(rec.get("check_in_method", "manual"))[:20],
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
                        # Resolver coordinador desde record offline
                        rec_coord = (rec.get("coordinator") or "").strip().upper() or None
                        if rec_coord:
                            assignment.admitted_by = rec_coord
                            if not assignment.programmed_by:
                                assignment.programmed_by = rec_coord
                        elif not assignment.admitted_by:
                            assignment.admitted_by = assignment.programmed_by
                        if can_set_uniform_batch:
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
        except IntegrityError as exc:
            # Race condition en batch: el constraint unico rechazo el insert
            logger.warning("Record #%d duplicado (race condition): %s", idx, exc.orig)
            failed += 1
        except Exception as exc:
            # Log sin exponer el payload completo (puede contener PII o internals)
            logger.error(
                "Error procesando record #%d (event_id=%s, operator_id=%s): %s",
                idx, event_id, operator_id, exc,
            )
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

    # --- Notificar por WebSocket (batch upload offline) ---
    await _notify_batch_checkin(session_event_id, synced, failed, len(records), user)

    return {
        "synced": synced,
        "failed": failed,
        "total": len(records),
        "sync_session_id": str(sync_session.id) if sync_session else None,
    }


async def _notify_batch_checkin(event_id, synced, failed, total, user):
    """Helper: notifica batch check-in por WebSocket (mejor reusabilidad)."""
    if synced <= 0:
        return
    try:
        await ws_manager.publish_broadcast(
            str(event_id), "checkin",
            {"batch": True, "synced": synced, "failed": failed, "total": total,
             "by": f"{user.first_name} {user.last_name}"},
        )
    except Exception as exc:
        logger.warning("[ws] no se pudo emitir batch checkin: %s", exc)


@router.get("/status")
async def sync_status(
    event_id: uuid.UUID = None,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """Get sync status for dashboard."""
    # Solo roles administrativos ven el historial de sincronización
    if user.user_type not in ("admin", "superadmin", "coordinator", "checkin", "operator"):
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
    await _resolve_staff_access(db, user, event_id)

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
    """Single check-in (online) manual."""
    staff_role = await _resolve_staff_access(db, user, event_id)

    operator_id = _to_uuid(payload.get("operator_id"))
    assignment_id = _to_uuid(payload.get("assignment_id"))
    method = payload.get("method", "manual")
    # Coordinator que admite al operador (opcional, desde selector UI)
    coordinator = (payload.get("coordinator") or "").strip().upper() or None
    # Optional uniform fields — solo checkin/admin/coordinator pueden setearlos
    can_set_uniform = _can_manage_uniform(user, staff_role)
    shirt_number = payload.get("shirt_number") if can_set_uniform else None
    jacket_number = payload.get("jacket_number") if can_set_uniform else None
    cap_number = payload.get("cap_number") if can_set_uniform else None

    if not operator_id:
        raise HTTPException(400, "operator_id requerido")

    # Check duplicate
    existing = await db.execute(
        select(AttendanceLog).where(
            AttendanceLog.event_id == event_id,
            AttendanceLog.operator_id == operator_id,
        )
    )
    existing_log = existing.scalar_one_or_none()
    if existing_log:
        # El operador ya tiene un log de asistencia. Pero si el assignment
        # NO está en checked_in, hay un estado inconsistente (deadlock):
        # el frontend recarga desde el servidor y ve status='confirmed',
        # así que el botón "Registrar Ingreso" vuelve a aparecer, pero al
        # clickear devuelve 409 de nuevo. Reconciliamos forzando checked_in.
        if assignment_id:
            assignment = await db.get(EventAssignment, assignment_id)
            if assignment and assignment.status != "checked_in":
                assignment.status = "checked_in"
                # Resolver coordinador (misma lógica del flujo normal)
                if coordinator:
                    assignment.admitted_by = coordinator
                    if not assignment.programmed_by:
                        assignment.programmed_by = coordinator
                elif not assignment.admitted_by:
                    assignment.admitted_by = assignment.programmed_by
                try:
                    await db.commit()
                except Exception as exc:
                    await db.rollback()
                    logger.error("Error reconciliando check-in: %s", exc)
        return {"status": "checked_in", "log_id": str(existing_log.id), "reconciled": True}

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
        verified_by=user.id,
        is_offline=False,
    )
    db.add(log)

    # Update assignment status to checked_in + save uniform
    if assignment_id:
        assignment = await db.get(EventAssignment, assignment_id)
        if assignment:
            # --- Resolver coordinador (admitted_by) ---
            # Prioridad: coordinator del payload > programmed_by > valor previo
            if coordinator:
                assignment.admitted_by = coordinator
                # Backfill programmed_by si estaba vacío (para historico)
                if not assignment.programmed_by:
                    assignment.programmed_by = coordinator
            elif not assignment.admitted_by:
                assignment.admitted_by = assignment.programmed_by

            # --- Validar cupo del coordinador (admitted_by) ---
            target_coord = assignment.admitted_by or assignment.programmed_by
            if target_coord:
                ok, msg, info = await _check_coordinator_quota(db, event_id, target_coord)
                if not ok:
                    # Listar coordinadores con cupo disponible para sugerir
                    suggestions = await _suggest_available_coordinators(db, event_id)
                    raise HTTPException(
                        409,
                        detail={
                            "error": "QUOTA_FULL",
                            "message": msg,
                            "coordinator": target_coord,
                            "suggestions": suggestions,
                        },
                    )

            assignment.status = "checked_in"
            if shirt_number is not None:
                assignment.shirt_number = shirt_number or None
            if jacket_number is not None:
                assignment.jacket_number = jacket_number or None
            if cap_number is not None:
                assignment.cap_number = cap_number or None

    try:
        await db.commit()
    except IntegrityError as exc:
        # Race condition: dos check-in simultaneos del mismo operador
        await db.rollback()
        logger.warning("Check-in duplicado (race condition) op=%s: %s", operator_id, exc.orig)
        raise HTTPException(409, "Operador ya registrado (concurrencia)")
    except Exception as exc:
        await db.rollback()
        safe_http_error(
            status_code=500,
            client_message="Error interno del servidor",
            log_detail="Error al guardar check-in",
            exc=exc,
        )

    # --- Notificar por WebSocket a las vistas en tiempo real ---
    try:
        await ws_manager.publish_broadcast(
            str(event_id),
            "checkin",
            {
                "operator_id": str(operator_id),
                "assignment_id": str(assignment_id) if assignment_id else None,
                "status": "checked_in",
                "method": method,
                "by": f"{user.first_name} {user.last_name}",
            },
        )
    except Exception as exc:
        logger.warning("[ws] no se pudo emitir evento checkin: %s", exc)

    return {"status": "checked_in", "log_id": str(log.id)}


async def _suggest_available_coordinators(db: AsyncSession, event_id: uuid.UUID):
    """Lista coordinadores con cupo disponible para sugerir reasignación."""
    quotas = await _get_coordinator_quotas(db, event_id)
    return [
        {"coordinator": q["coordinator"], "available": q["available"], "quota": q["quota"]}
        for q in quotas
        if q["available"] > 0
    ]


@router.get("/events/{event_id}/coordinator-quotas")
async def get_coordinator_quotas_endpoint(
    event_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """Endpoint público (autenticado) para obtener cupos + conteo en vivo.

    Usado por las tarjetas UI de check-in para mostrar el estado de cada
    coordinador en tiempo real.
    """
    await _resolve_staff_access(db, user, event_id)

    quotas = await _get_coordinator_quotas(db, event_id)
    return {
        "event_id": str(event_id),
        "quotas": quotas,
        "updated_at": datetime.utcnow().isoformat(),
    }


@router.patch("/assignments/{assignment_id}/reassign")
async def reassign_coordinator(
    assignment_id: uuid.UUID,
    payload: dict,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """Reasigna un operador a otro coordinador (cambia admitted_by).

    Permite mover un operador cuando su coordinador original está lleno.
    Solo actualiza admitted_by; el programmed_by se conserva histórico.
    """
    new_coordinator = (payload.get("new_coordinator") or "").strip().upper()
    if not new_coordinator:
        raise HTTPException(400, "new_coordinator requerido")

    # reason opcional para el audit log (distingue cambios manuales post-checkin)
    reason = (payload.get("reason") or "").strip() or "Cupo lleno - reasignación automática en check-in"

    assignment = await db.get(EventAssignment, assignment_id)
    if not assignment:
        raise HTTPException(404, "Asignación no encontrada")

    # Validar permisos de staff para el evento de la asignación
    await _resolve_staff_access(db, user, assignment.event_id)

    # Verificar cupo del nuevo coordinador
    ok, msg, info = await _check_coordinator_quota(db, assignment.event_id, new_coordinator)
    if not ok:
        raise HTTPException(409, detail={"error": "QUOTA_FULL", "message": msg})

    old = assignment.admitted_by
    assignment.admitted_by = new_coordinator

    try:
        await db.commit()
    except Exception as exc:
        await db.rollback()
        safe_http_error(
            status_code=500,
            client_message="Error interno del servidor",
            log_detail="Error en reasignación de coordinador",
            exc=exc,
        )

    # --- Registrar cesión en audit log ---
    try:
        from app.services.events import _add_audit_log
        await _add_audit_log(
            db,
            event_id=assignment.event_id,
            user_id=user.id,
            action="coordinator_reassign",
            changes={
                "assignment_id": str(assignment.id),
                "operator_id": str(assignment.operator_id),
                "old_coordinator": old,
                "new_coordinator": new_coordinator,
                "reason": reason,
            },
        )
        await db.commit()
    except Exception as exc:
        await db.rollback()
        logger.warning("No se pudo registrar audit log de reasignación: %s", exc)

    # --- Notificar por WebSocket (reasignación de coordinador) ---
    try:
        await ws_manager.publish_broadcast(
            str(assignment.event_id),
            "reassign",
            {
                "assignment_id": str(assignment.id),
                "old_coordinator": old,
                "new_coordinator": new_coordinator,
            },
        )
    except Exception as exc:
        logger.warning("[ws] no se pudo emitir reassign: %s", exc)

    return {
        "status": "reassigned",
        "assignment_id": str(assignment.id),
        "old_coordinator": old,
        "new_coordinator": new_coordinator,
        "message": f"{old or 'Sin coordinador'} cedió el operador a {new_coordinator}",
    }


@router.patch("/assignments/{assignment_id}/uniform")
async def update_uniform(
    assignment_id: uuid.UUID,
    payload: dict,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """Edita la indumentaria asignada a un operador (incluso después del check-in)."""
    assignment = await db.get(EventAssignment, assignment_id)
    if not assignment:
        raise HTTPException(404, "Asignación no encontrada")

    staff_role = await _resolve_staff_access(
        db, user, assignment.event_id, allow_checkin=True
    )
    if not _can_manage_uniform(user, staff_role):
        raise HTTPException(403, "Sin permisos para editar indumentaria")

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

    try:
        await db.commit()
    except IntegrityError as exc:
        # Race condition: dos staff asignaron el mismo numero
        await db.rollback()
        logger.warning("Conflicto de uniform (race condition) assignment=%s: %s", assignment_id, exc.orig)
        raise HTTPException(409, "Número de indumentaria ya asignado a otro operador (concurrencia)")

    # Recargar para reflejar el estado final commiteado
    await db.refresh(assignment)

    # --- Notificar por WebSocket (indumentaria actualizada) ---
    try:
        await ws_manager.publish_broadcast(
            str(assignment.event_id),
            "uniform",
            {
                "assignment_id": str(assignment.id),
                "shirt_number": assignment.shirt_number,
                "jacket_number": assignment.jacket_number,
                "cap_number": assignment.cap_number,
                "by": f"{user.first_name} {user.last_name}",
            },
        )
    except Exception as exc:
        logger.warning("[ws] no se pudo emitir uniform_update: %s", exc)

    return {
        "status": "updated",
        "assignment_id": str(assignment.id),
        "shirt_number": assignment.shirt_number,
        "jacket_number": assignment.jacket_number,
        "cap_number": assignment.cap_number,
    }


async def _build_coordinator_map(db: AsyncSession, event_id: uuid.UUID):
    """Construye el mapeo de coordinadores para un evento (Opción A: por área).

    Retorna:
        area_to_coord: dict {area: (coordinator_full_name, role_name)}
        general_coord: tuple (name, role_name) del Coordinador General (nivel 1) o None
    """
    from app.models.roles import Role

    # Buscar asignaciones del evento cuyo rol sea coordinador (nivel <= 2)
    result = await db.execute(
        select(EventAssignment, Operator, User, Role)
        .join(Operator, Operator.id == EventAssignment.operator_id)
        .join(User, User.id == Operator.user_id)
        .join(Role, Role.id == EventAssignment.role_id)
        .where(
            EventAssignment.event_id == event_id,
            Role.hierarchy_level <= 2,
        )
    )

    area_to_coord = {}
    general_coord = None
    for assignment, operator, op_user, role in result.all():
        full_name = f"{op_user.first_name} {op_user.last_name}"
        if role.hierarchy_level == 1:
            # Coordinador General — fallback global
            general_coord = (full_name, role.name)
        elif role.area:
            # Coordinador de área — mapea área -> coordinador
            if role.area not in area_to_coord:
                area_to_coord[role.area] = (full_name, role.name)

    return area_to_coord, general_coord


def _register_presence(event_id: str, device_id: str, user_name: str):
    """Registra que un dispositivo está viendo el check-in del evento (Fase 3)."""
    if not device_id:
        device_id = "anon"
    now = time.time()
    if event_id not in _checkin_presence:
        _checkin_presence[event_id] = {}
    _checkin_presence[event_id][device_id] = (now, user_name)


def _get_active_viewers(event_id: str):
    """Cuenta y lista dispositivos activos en el check-in del evento (Fase 3).

    Un dispositivo se considera activo si hizo polling en los últimos
    PRESENCE_TTL_SECONDS segundos (default 15s).
    """
    now = time.time()
    presence = _checkin_presence.get(event_id, {})
    active = {
        did: (ts, name)
        for did, (ts, name) in presence.items()
        if now - ts <= PRESENCE_TTL_SECONDS
    }
    _checkin_presence[event_id] = active
    viewers = [
        {"device_id": did, "user_name": name}
        for did, (_, name) in active.items()
    ]
    return len(active), viewers


@router.get("/events/{event_id}/checkin-status")
async def get_checkin_status(
    event_id: uuid.UUID,
    device_id: str = Query(default=None, description="ID del dispositivo (Fase 3)"),
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """Endpoint ligero para polling en tiempo real del check-in (Fase 1 + Fase 3).

    Fase 1: retorna solo status + uniform por asignación (payload pequeño).
    Fase 3: registra presencia del dispositivo y retorna:
      - active_viewers: cuántas personas están viendo el check-in ahora
      - recent_activity: últimos ingresos registrados (en cualquier dispositivo)
    """
    await _resolve_staff_access(db, user, event_id)

    # --- Fase 3: registrar presencia ---
    viewer_name = f"{user.first_name} {user.last_name}" if getattr(user, "first_name", None) else (user.email or "Usuario")
    _register_presence(str(event_id), device_id or "anon", viewer_name)
    active_count, viewers = _get_active_viewers(str(event_id))

    # --- Fase 1: status + uniform por asignación ---
    result = await db.execute(
        select(EventAssignment)
        .where(EventAssignment.event_id == event_id)
    )
    assignments = result.scalars().all()

    # --- Fase 3: log compartido de ingresos recientes (otros dispositivos) ---
    recent_activity = []
    try:
        recent_result = await db.execute(
            select(AttendanceLog, Operator)
            .join(Operator, Operator.id == AttendanceLog.operator_id)
            .where(AttendanceLog.event_id == event_id)
            .order_by(AttendanceLog.check_in_time.desc())
            .limit(15)
        )
        for log, op in recent_result.all():
            recent_activity.append({
                "operator_name": f"{op.user.first_name} {op.user.last_name}" if op.user else "—",
                "check_in_time": log.check_in_time.isoformat() if log.check_in_time else None,
                "method": log.check_in_method,
            })
    except Exception:
        # No bloquear el polling si falla el log
        pass

    return {
        "event_id": str(event_id),
        "updated_at": datetime.utcnow().isoformat(),
        "active_viewers": active_count,
        "viewers": viewers,
        "recent_activity": recent_activity,
        "assignments": [
            {
                "id": str(a.id),
                "status": a.status,
                "shirt_number": a.shirt_number,
                "jacket_number": a.jacket_number,
                "cap_number": a.cap_number,
            }
            for a in assignments
        ],
    }
