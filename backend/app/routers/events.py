"""Event router - API endpoints for event management."""
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app import permissions
from app.database import get_db
from app.dependencies.auth import get_current_user
from app.models.users import User
from app.schemas.events import (
    EventCreate, EventUpdate, EventResponse, EventListResponse,
    AssignmentResponse, AssignOperatorsRequest,
    ImportSummary, DeleteEventRequest,
    ImportJobAccepted, ImportJobStatus,
    QuickAddRequest, QuickAddResponse,
)
from app.services import events as svc
from app.services import operator_import as imp_svc
from app.services import import_jobs
from app.services import quick_add as qa_svc

router = APIRouter(prefix="/api/events", tags=["events"])


@router.post("/", response_model=EventResponse, status_code=201)
async def create_event(
    data: EventCreate,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """Create a new event with staff needs."""
    if user.user_type not in ("superadmin", "admin"):
        raise HTTPException(403, "Sin permisos para crear eventos")
    event = await svc.create_event(db, data, user.id)
    result = await svc.get_event(db, event.id)
    return result


@router.get("/", response_model=EventListResponse)
async def list_events(
    status: Optional[str] = Query(None),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """List events with optional status filter."""
    if not permissions.can_view_monitoring(user):
        raise HTTPException(403, "Sin permisos")
    items, total = await svc.list_events(db, status=status, limit=limit, offset=offset)
    return EventListResponse(items=items, total=total)


@router.get("/{event_id}", response_model=EventResponse)
async def get_event(
    event_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """Get event detail."""
    if not permissions.can_view_monitoring(user):
        raise HTTPException(403, "Sin permisos")
    result = await svc.get_event(db, event_id)
    if not result:
        raise HTTPException(404, "Evento no encontrado")
    return result


@router.put("/{event_id}", response_model=EventResponse)
async def update_event(
    event_id: uuid.UUID,
    data: EventUpdate,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """Update an event."""
    if user.user_type not in ("superadmin", "admin"):
        raise HTTPException(403, "Sin permisos")
    event = await svc.update_event(db, event_id, data, user_id=user.id)
    if not event:
        raise HTTPException(404, "Evento no encontrado")
    result = await svc.get_event(db, event_id)
    return result


@router.delete("/{event_id}")
async def delete_event(
    event_id: uuid.UUID,
    data: DeleteEventRequest,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """Elimina un evento. Solo superadmin y con confirmación de contraseña.

    El cuerpo debe incluir la contraseña de acceso del superadmin
    ({"password": "..."}) como doble factor de confirmación.
    """
    if user.user_type != "superadmin":
        raise HTTPException(403, "Solo un superadmin puede eliminar eventos")
    from app.services.auth import verify_password
    if not verify_password(data.password, user.password_hash):
        raise HTTPException(403, "Contraseña incorrecta. Eliminación cancelada.")
    ok = await svc.delete_event(db, event_id)
    if not ok:
        raise HTTPException(404, "Evento no encontrado")
    return {"message": "Evento eliminado"}


# ============================================================
# IMPORTACIÓN MASIVA DESDE EXCEL
# ============================================================

@router.get("/import/template")
async def download_import_template(
    user=Depends(get_current_user),
):
    """Descarga la plantilla Excel (.xlsx) para importación masiva de operadores."""
    if user.user_type not in ("superadmin", "admin"):
        raise HTTPException(403, "Sin permisos")
    file_bytes = imp_svc.build_template()
    return Response(
        content=file_bytes,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": 'attachment; filename="plantilla_operadores.xlsx"',
        },
    )


@router.post("/{event_id}/import-operators", response_model=ImportJobAccepted, status_code=202)
async def import_operators_excel(
    event_id: uuid.UUID,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """Importa operadores masivamente desde un Excel (.xlsx) — ASÍNCRONO.

    Archivos grandes (1000+ filas) tardan minutos (bcrypt por operador) y
    excedían el timeout de nginx/Cloudflare: el loader desaparecía sin
    respuesta. Ahora el POST valida y responde 202 de inmediato con un
    ``job_id``; el Excel se procesa en background y el frontend consulta
    el progreso con GET /api/events/import/status/{job_id}.
    """
    if user.user_type not in ("superadmin", "admin"):
        raise HTTPException(403, "Sin permisos")
    event = await svc.get_event(db, event_id)
    if not event:
        raise HTTPException(404, "Evento no encontrado")

    # Validar extensión
    filename = (file.filename or "").lower()
    if not filename.endswith(".xlsx"):
        raise HTTPException(400, "El archivo debe ser .xlsx")

    file_bytes = await file.read()
    if not file_bytes:
        raise HTTPException(400, "Archivo vacío")

    job_id = import_jobs.start_import_job(event_id, file_bytes)
    return ImportJobAccepted(
        job_id=job_id,
        status="queued",
        status_url=f"/api/events/import/status/{job_id}",
    )


@router.get("/import/status/{job_id}", response_model=ImportJobStatus)
async def get_import_status(
    job_id: str,
    user=Depends(get_current_user),
):
    """Progreso/resultado de un job de importación en background.

    status: queued | running | completed | failed.
    Al completar incluye el ImportSummary completo (métricas + filas).
    """
    if user.user_type not in ("superadmin", "admin"):
        raise HTTPException(403, "Sin permisos")
    status = import_jobs.get_job_status(job_id)
    if status is None:
        raise HTTPException(404, "Job no encontrado o expirado (TTL 1h)")
    return status


@router.post("/{event_id}/assign")
async def assign_operators(
    event_id: uuid.UUID,
    data: AssignOperatorsRequest,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """Assign operators to an event."""
    if user.user_type not in ("superadmin", "admin"):
        raise HTTPException(403, "Sin permisos")
    # Verify event exists
    event = await svc.get_event(db, event_id)
    if not event:
        raise HTTPException(404, "Evento no encontrado")
    assignments, unavailable = await svc.assign_operators(
        db, event_id, data.operator_ids, data.role_id, data.rate_applied,
        programmed_by_operator_id=data.programmed_by_operator_id,
        programmed_by_name=data.programmed_by_name,
        stage=data.stage,
    )
    # Return updated assignments + any conflicts
    all_assignments = await svc.get_assignments(db, event_id)
    result = {"assignments": all_assignments, "unavailable": unavailable}
    return result


@router.get("/{event_id}/coordinators")
async def get_event_coordinators(
    event_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """Lista los coordinadores asignados a un evento con su cupo/ocupado.
    Devuelve el EventCoordinatorQuota con conteos calculados."""
    if user.user_type not in ("superadmin", "admin"):
        raise HTTPException(403, "Sin permisos")
    event = await svc.get_event(db, event_id)
    if not event:
        raise HTTPException(404, "Evento no encontrado")
    return event.get("coordinator_quotas", [])


@router.post("/{event_id}/check-availability")
async def check_availability(
    event_id: uuid.UUID,
    data: AssignOperatorsRequest,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """Check which operators are available for an event (no double-booking)."""
    if user.user_type not in ("superadmin", "admin"):
        raise HTTPException(403, "Sin permisos")
    event = await svc.get_event(db, event_id)
    if not event:
        raise HTTPException(404, "Evento no encontrado")

    from app.models.events import EventAssignment, Event as EventModel
    from app.models.operators import Operator as OpModel
    from sqlalchemy import select as sel

    current_event = await db.get(EventModel, event_id)
    results = {"available": [], "unavailable": []}

    for uid in data.operator_ids:
        op_r = await db.execute(sel(OpModel).where((OpModel.id == uid) | (OpModel.user_id == uid)))
        operator = op_r.scalar_one_or_none()
        if not operator:
            continue
        # Get user info
        u_r = await db.execute(sel(User).where(User.id == operator.user_id))
        op_user = u_r.scalar_one_or_none()
        name = f"{op_user.first_name} {op_user.last_name}" if op_user else "N/A"

        overlap = await db.execute(
            sel(EventAssignment)
            .join(EventModel, EventAssignment.event_id == EventModel.id)
            .where(
                EventAssignment.operator_id == operator.id,
                EventAssignment.status.in_(["invited", "confirmed", "checked_in", "standby"]),
                EventAssignment.event_id != event_id,
                EventModel.status.in_(["draft", "published", "in_progress"]),
                EventModel.start_date < current_event.end_date,
                EventModel.end_date > current_event.start_date,
            )
        )
        conflict = overlap.scalars().first()
        if conflict:
            conflict_event = await db.get(EventModel, conflict.event_id)
            results["unavailable"].append({
                "operator_id": str(operator.id),
                "user_id": str(operator.user_id),
                "name": name,
                "conflict_event": conflict_event.name if conflict_event else "N/A",
            })
        else:
            results["available"].append({
                "operator_id": str(operator.id),
                "user_id": str(operator.user_id),
                "name": name,
            })
    return results


@router.get("/{event_id}/audit-logs")
async def get_audit_logs(
    event_id: uuid.UUID,
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """Get audit logs for an event."""
    if user.user_type not in ("superadmin", "admin"):
        raise HTTPException(403, "Sin permisos")
    return await svc.get_audit_logs(db, event_id, limit=limit)


# Ruta estรกtica ANTES de las dinรกmicas /{event_id} para que no colisione
@router.get("/my-events/staff")
async def get_my_staff_events(
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """Lista los eventos donde el usuario actual está asignado como staff (checkin).
    También incluye todos los eventos si es superadmin."""
    from sqlalchemy import select as sel
    from app.models.events import EventStaffAssignment, Event as EventModel

    from app.models.events import EventCoordinatorQuota
    from app.models.operators import Operator as OpModel

    # Superadmin y admin (management) ven todos los eventos
    if user.user_type in ("superadmin", "admin"):
        result = await db.execute(
            sel(EventModel)
            .where(EventModel.is_active == True, EventModel.status.in_(["draft", "published", "in_progress"]))
            .order_by(EventModel.start_date.desc())
        )
        events = result.scalars().all()
        return [
            {
                "id": str(e.id),
                "name": e.name,
                "location": e.location,
                "start_date": e.start_date.isoformat() if e.start_date else None,
                "status": e.status,
                "staff_role": "superadmin",
            }
            for e in events
        ]

    # Coordinador: eventos donde tiene cupo (EventCoordinatorQuota) +
    # eventos asignados como staff (checkin).
    if user.user_type == "coordinator":
        # Buscar el Operator asociado a este usuario (coordinador-operador)
        op_r = await db.execute(sel(OpModel).where(OpModel.user_id == user.id))
        my_operator = op_r.scalar_one_or_none()

        seen_event_ids = set()
        out = []

        # 1) Eventos donde tengo cupo de coordinador
        if my_operator:
            q_r = await db.execute(
                sel(EventModel, EventCoordinatorQuota)
                .join(EventCoordinatorQuota, EventCoordinatorQuota.event_id == EventModel.id)
                .where(
                    EventCoordinatorQuota.coordinator_operator_id == my_operator.id,
                    EventModel.is_active == True,
                    EventModel.status.in_(["draft", "published", "in_progress"]),
                )
                .order_by(EventModel.start_date.desc())
            )
            for e, q in q_r.all():
                if e.id in seen_event_ids:
                    continue
                seen_event_ids.add(e.id)
                out.append({
                    "id": str(e.id),
                    "name": e.name,
                    "location": e.location,
                    "start_date": e.start_date.isoformat() if e.start_date else None,
                    "status": e.status,
                    "staff_role": "coordinator",
                })

        # 2) Eventos asignados como staff (checkin)
        sa_r = await db.execute(
            sel(EventModel, EventStaffAssignment)
            .join(EventStaffAssignment, EventStaffAssignment.event_id == EventModel.id)
            .where(
                EventStaffAssignment.user_id == user.id,
                EventStaffAssignment.is_active == True,
                EventModel.is_active == True,
            )
            .order_by(EventModel.start_date.desc())
        )
        for e, sa in sa_r.all():
            if e.id in seen_event_ids:
                continue
            seen_event_ids.add(e.id)
            out.append({
                "id": str(e.id),
                "name": e.name,
                "location": e.location,
                "start_date": e.start_date.isoformat() if e.start_date else None,
                "status": e.status,
                "staff_role": sa.staff_role,
            })
        return out

    # checkin / operator: solo eventos asignados como staff
    result = await db.execute(
        sel(EventModel, EventStaffAssignment)
        .join(EventStaffAssignment, EventStaffAssignment.event_id == EventModel.id)
        .where(
            EventStaffAssignment.user_id == user.id,
            EventStaffAssignment.is_active == True,
            EventModel.is_active == True,
        )
        .order_by(EventModel.start_date.desc())
    )
    rows = result.all()
    return [
        {
            "id": str(e.id),
            "name": e.name,
            "location": e.location,
            "start_date": e.start_date.isoformat() if e.start_date else None,
            "status": e.status,
            "staff_role": sa.staff_role,
        }
        for e, sa in rows
    ]


@router.post("/{event_id}/quick-add", response_model=QuickAddResponse, status_code=201)
async def quick_add(
    event_id: uuid.UUID,
    data: QuickAddRequest,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """⚡ Incorporación Rápida: registra una persona de última hora en el evento.

    Crea un operador "solo evento" (usuario fantasma inactivo, sin email,
    contraseña aleatoria) y lo asigna con status='confirmed' a la etapa
    'evento'. Si el documento ya existe como operador REAL, asigna al
    existente (mode="existing"). El ghost se purga automáticamente al
    quedar sin asignaciones activas.
    """
    # Roles que pueden incorporar personal de última hora: management,
    # coordinadores y el staff de Check-in e Indumentaria (intendencia
    # quedó fusionada en check-in). Ver permissions.py.
    if user.user_type not in ("superadmin", "admin", "coordinator", "checkin", "intendencia"):
        raise HTTPException(403, "Sin permisos")
    event = await svc.get_event(db, event_id)
    if not event:
        raise HTTPException(404, "Evento no encontrado")
    admin_display = f"{user.first_name} {user.last_name}".upper().strip()
    return await qa_svc.quick_add_operator(db, event_id, data, admin_display=admin_display)


@router.get("/{event_id}/assignments", response_model=list[AssignmentResponse])
async def get_assignments(
    event_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """Get all assignments for an event.
    Operadores asignados como staff (checkin) también pueden verlas."""
    if user.user_type not in ("superadmin", "admin", "checkin", "intendencia"):
        # Operador: validar asignación de staff para este evento
        from sqlalchemy import select as sel
        from app.models.events import EventStaffAssignment
        sa_r = await db.execute(
            sel(EventStaffAssignment).where(
                EventStaffAssignment.event_id == event_id,
                EventStaffAssignment.user_id == user.id,
                EventStaffAssignment.is_active == True,
            )
        )
        if not sa_r.scalar_one_or_none():
            raise HTTPException(403, "Sin permisos")
    return await svc.get_assignments(db, event_id)


# ============================================================
# STAFF ASSIGNMENTS (checkin)
# ============================================================

@router.get("/{event_id}/staff")
async def get_event_staff(
    event_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """Lista el personal (checkin) asignado a un evento."""
    if user.user_type not in ("superadmin", "admin"):
        raise HTTPException(403, "Sin permisos")
    from sqlalchemy import select as sel
    from app.models.events import EventStaffAssignment

    result = await db.execute(
        sel(EventStaffAssignment, User)
        .join(User, EventStaffAssignment.user_id == User.id)
        .where(EventStaffAssignment.event_id == event_id, EventStaffAssignment.is_active == True)
    )
    rows = result.all()
    return [
        {
            "id": str(sa.id),
            "user_id": str(sa.user_id),
            "staff_role": sa.staff_role,
            "full_name": f"{u.first_name} {u.last_name}",
            "document_number": u.document_number,
        }
        for sa, u in rows
    ]


@router.post("/{event_id}/staff")
async def set_event_staff(
    event_id: uuid.UUID,
    data: dict,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """Reemplaza TODA la asignación de staff de un evento.
    Body: {"checkin": [user_id, ...]}
    """
    if user.user_type not in ("superadmin", "admin"):
        raise HTTPException(403, "Sin permisos")
    from sqlalchemy import select as sel, delete
    from app.models.events import EventStaffAssignment

    # Verificar que el evento existe
    event = await svc.get_event(db, event_id)
    if not event:
        raise HTTPException(404, "Evento no encontrado")

    # Eliminar asignaciones previas
    await db.execute(
        delete(EventStaffAssignment).where(EventStaffAssignment.event_id == event_id)
    )

    created = 0
    # 'intendencia' se normaliza a 'checkin' (roles fusionados funcionalmente).
    VALID_STAFF_ROLES = {"checkin", "intendencia"}
    for staff_role, user_ids in data.items():
        if staff_role not in VALID_STAFF_ROLES:
            continue
        effective_role = "checkin" if staff_role == "intendencia" else staff_role
        for uid_str in (user_ids or []):
            try:
                uid = uuid.UUID(str(uid_str))
            except (ValueError, TypeError):
                continue
            sa = EventStaffAssignment(
                event_id=event_id,
                user_id=uid,
                staff_role=effective_role,
            )
            db.add(sa)
            created += 1

    await db.commit()
    return {"message": "Staff asignado", "count": created}


@router.delete("/assignments/{assignment_id}")
async def delete_assignment(
    assignment_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """Elimina (desasigna) un operador de un evento.
    Solo superadmin/coordinator. Borra el registro de asignaciรณn."""
    if user.user_type not in ("superadmin", "admin"):
        raise HTTPException(403, "Sin permisos")
    from sqlalchemy import select as sel
    from app.models.events import EventAssignment

    result = await db.execute(sel(EventAssignment).where(EventAssignment.id == assignment_id))
    assignment = result.scalar_one_or_none()
    if not assignment:
        raise HTTPException(404, "Asignaciรณn no encontrada")

    # Si estaba confirmado, decrementar quantity_confirmed del EventStaffNeed
    # (del need de la MISMA etapa de la asignación; fallback a cualquier etapa).
    if assignment.status == "confirmed" and assignment.role_id:
        from app.models.events import EventStaffNeed
        stage = getattr(assignment, "stage", None) or "evento"
        sn_r = await db.execute(
            sel(EventStaffNeed).where(
                EventStaffNeed.event_id == assignment.event_id,
                EventStaffNeed.role_id == assignment.role_id,
                EventStaffNeed.stage == stage,
            )
        )
        sn = sn_r.scalar_one_or_none()
        if not sn:
            sn_r = await db.execute(
                sel(EventStaffNeed).where(
                    EventStaffNeed.event_id == assignment.event_id,
                    EventStaffNeed.role_id == assignment.role_id,
                )
            )
            sn = sn_r.scalar_one_or_none()
        if sn:
            sn.quantity_confirmed = max(sn.quantity_confirmed - 1, 0)

    await db.delete(assignment)
    await db.commit()

    # Purga de ghosts: si era un operador "solo evento" y esta era su
    # única asignación activa, se elimina junto con su usuario fantasma.
    from app.services.quick_add import purge_orphan_event_only_operators
    await purge_orphan_event_only_operators(db)

    return {"message": "Operador desasignado del evento"}


@router.patch("/assignments/{assignment_id}/uniform")
async def update_assignment_uniform(
    assignment_id: uuid.UUID,
    data: dict,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """Actualiza campos de uniforme (shirt_number, jacket_number, cap_number).
    Accesible para superadmin, coordinator, checkin u operador asignado como checkin."""
    from sqlalchemy import select as sel
    from app.models.events import EventAssignment, EventStaffAssignment

    result = await db.execute(sel(EventAssignment).where(EventAssignment.id == assignment_id))
    assignment = result.scalar_one_or_none()
    if not assignment:
        raise HTTPException(404, "Asignación no encontrada")

    # Validar permisos
    if user.user_type not in ("superadmin", "admin", "checkin", "intendencia"):
        # Operador: debe tener asignación de staff checkin para este evento
        sa_r = await db.execute(
            sel(EventStaffAssignment).where(
                EventStaffAssignment.event_id == assignment.event_id,
                EventStaffAssignment.user_id == user.id,
                EventStaffAssignment.staff_role == "checkin",
                EventStaffAssignment.is_active == True,
            )
        )
        if not sa_r.scalar_one_or_none():
            raise HTTPException(403, "Sin permisos")

    for field in ("shirt_number", "jacket_number", "cap_number"):
        if field in data:
            val = data[field]
            setattr(assignment, field, val if val else None)

    await db.commit()
    return {"message": "Indumentaria actualizada"}


@router.patch("/assignments/{assignment_id}/checkin")
async def checkin_assignment(
    assignment_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """Marca un operador como 'checked_in' (ingreso al evento).
    Accesible para superadmin, coordinator, checkin u operador asignado como checkin."""
    from sqlalchemy import select as sel
    from app.models.events import EventAssignment, EventStaffAssignment

    result = await db.execute(sel(EventAssignment).where(EventAssignment.id == assignment_id))
    assignment = result.scalar_one_or_none()
    if not assignment:
        raise HTTPException(404, "Asignaciรณn no encontrada")

    # Validar permisos
    if user.user_type not in ("superadmin", "admin", "checkin", "intendencia"):
        # Operador: debe tener asignaciรณn de staff checkin para este evento
        sa_r = await db.execute(
            sel(EventStaffAssignment).where(
                EventStaffAssignment.event_id == assignment.event_id,
                EventStaffAssignment.user_id == user.id,
                EventStaffAssignment.staff_role == "checkin",
                EventStaffAssignment.is_active == True,
            )
        )
        if not sa_r.scalar_one_or_none():
            raise HTTPException(403, "Sin permisos")

    # Solo se puede hacer check-in si estรก confirmed o standby
    if assignment.status not in ("confirmed", "standby"):
        raise HTTPException(400, f"No se puede hacer check-in: el operador estรก '{assignment.status}'")

    assignment.status = "checked_in"
    await db.commit()
    return {"message": "Check-in realizado", "status": "checked_in"}
