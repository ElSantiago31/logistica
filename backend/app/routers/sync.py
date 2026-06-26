"""Sync router — offline data download + attendance batch upload."""
import logging
import time
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies.auth import get_current_user
from app.models.events import Event, EventAssignment, EventStaffNeed, EventCoordinatorQuota
from app.models.operators import Operator
from app.models.sync import SyncSession, AttendanceLog
from app.models.users import User

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


@router.get("/events/{event_id}/offline-data")
async def get_offline_data(
    event_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """Download event data for offline PWA use."""
    if user.user_type not in ("admin", "superadmin", "coordinator", "checkin", "intendencia"):
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

    out = []
    for q in quotas:
        ci = checked_in_counts.get(q.coordinator, 0)
        pg = programmed_counts.get(q.coordinator, 0)
        out.append({
            "coordinator": q.coordinator,
            "quota": q.quota,
            "checked_in": ci,
            "programmed": pg,
            "available": q.quota - ci,
            "full": ci >= q.quota,
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
    if user.user_type not in ("admin", "superadmin", "coordinator", "checkin", "intendencia"):
        raise HTTPException(403, "Sin permisos")

    records = payload.get("records", [])
    if not records:
        return {"synced": 0, "failed": 0, "total": 0}

    session_event_id = _to_uuid(records[0].get("event_id"))
    if not session_event_id:
        raise HTTPException(400, "event_id inválido o vacío en records[0]")

    # Rol checkin no puede setear indumentaria en sync batch
    can_set_uniform_batch = user.user_type in ("admin", "superadmin", "coordinator", "intendencia")

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
            logger.error("Error procesando record #%d: %s - %s", idx, exc, rec)
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
    if user.user_type not in ("admin", "superadmin", "coordinator", "checkin", "intendencia"):
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
    if user.user_type not in ("admin", "superadmin", "coordinator", "checkin", "intendencia"):
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
    if user.user_type not in ("admin", "superadmin", "coordinator", "checkin", "intendencia"):
        raise HTTPException(403, "Sin permisos")

    operator_id = _to_uuid(payload.get("operator_id"))
    assignment_id = _to_uuid(payload.get("assignment_id"))
    method = payload.get("method", "manual")
    code = payload.get("scanned_code")
    # Optional uniform fields — solo intendencia/admin/coordinator pueden setearlos
    can_set_uniform = user.user_type in ("admin", "superadmin", "coordinator", "intendencia")
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
            # Asegurar admitted_by (default = programmed_by)
            if not assignment.admitted_by:
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
        logger.error("Error en check-in: %s", exc)
        raise HTTPException(500, f"Error al guardar check-in: {exc}")

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
    if user.user_type not in ("admin", "superadmin", "coordinator", "checkin", "intendencia"):
        raise HTTPException(403, "Sin permisos")

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
    if user.user_type not in ("admin", "superadmin", "coordinator"):
        raise HTTPException(403, "Sin permisos")

    new_coordinator = (payload.get("new_coordinator") or "").strip().upper()
    if not new_coordinator:
        raise HTTPException(400, "new_coordinator requerido")

    assignment = await db.get(EventAssignment, assignment_id)
    if not assignment:
        raise HTTPException(404, "Asignación no encontrada")

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
        logger.error("Error en reasignación: %s", exc)
        raise HTTPException(500, f"Error al reasignar: {exc}")

    return {
        "status": "reassigned",
        "assignment_id": str(assignment.id),
        "old_coordinator": old,
        "new_coordinator": new_coordinator,
    }


@router.patch("/assignments/{assignment_id}/uniform")
async def update_uniform(
    assignment_id: uuid.UUID,
    payload: dict,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """Edita la indumentaria asignada a un operador (incluso después del check-in)."""
    if user.user_type not in ("admin", "superadmin", "coordinator", "intendencia"):
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

    try:
        await db.commit()
    except IntegrityError as exc:
        # Race condition: dos intendencia asignaron el mismo numero
        await db.rollback()
        logger.warning("Conflicto de uniform (race condition) assignment=%s: %s", assignment_id, exc.orig)
        raise HTTPException(409, "Número de indumentaria ya asignado a otro operador (concurrencia)")

    # Recargar para reflejar el estado final commiteado
    await db.refresh(assignment)

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
    if user.user_type not in ("admin", "superadmin", "coordinator", "checkin", "intendencia"):
        raise HTTPException(403, "Sin permisos")

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
