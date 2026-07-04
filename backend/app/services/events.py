"""Event service - CRUD and assignment logic."""
import json
import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional, List

# Colombia timezone (UTC-5)
COLOMBIA_TZ = timezone(timedelta(hours=-5))

from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.events import Event, EventStaffNeed, EventAssignment, EventAuditLog, EventCoordinatorQuota
from app.models.operators import Operator
from app.models.roles import Role
from app.models.users import User
from app.schemas.events import EventCreate, EventUpdate


async def _add_audit_log(db: AsyncSession, event_id: uuid.UUID, user_id: uuid.UUID,
                         action: str, changes: dict = None):
    """Helper to create an audit log entry."""
    user_result = await db.execute(select(User).where(User.id == user_id))
    user = user_result.scalar_one_or_none()
    user_name = f"{user.first_name} {user.last_name}" if user else "Sistema"
    log = EventAuditLog(
        event_id=event_id,
        user_id=user_id,
        action=action,
        changes=json.dumps(changes, ensure_ascii=False, default=str) if changes else None,
        user_name=user_name,
    )
    db.add(log)


async def _resolve_coordinator(db: AsyncSession, any_id: uuid.UUID) -> Optional[Operator]:
    """Resuelve un operador-coordinador a partir de un ID que puede ser
    `operators.id` o `users.id` (user_id). Devuelve el objeto Operator o None.

    El frontend históricamente envía el user_id (lo que devuelve /api/operators
    como `id`), mientras que las FKs apuntan a operators.id. Esta función
    tolera ambos para evitar ForeignKeyViolationError.
    """
    result = await db.execute(
        select(Operator).where(
            (Operator.id == any_id) | (Operator.user_id == any_id)
        )
    )
    return result.scalar_one_or_none()


async def _resolve_coordinator_name(db: AsyncSession, any_id: uuid.UUID) -> Optional[str]:
    """Resuelve el nombre en MAYÚSCULAS del operador-coordinador.

    Acepta `operator_id` (operators.id) o `user_id` (users.id).
    """
    operator = await _resolve_coordinator(db, any_id)
    if not operator:
        return None
    u_result = await db.execute(select(User).where(User.id == operator.user_id))
    user = u_result.scalar_one_or_none()
    if not user:
        return None
    return f"{user.first_name} {user.last_name}".upper()


async def _save_coordinator_quotas(
    db: AsyncSession, event_id: uuid.UUID, quotas_data: list,
) -> List[dict]:
    """Reemplaza las quotas de coordinadores de un evento (delete + insert).

    `quotas_data` es una lista de dicts: [{operator_id, quota}, ...].
    Devuelve un resumen para el audit log.
    """
    # Borrar quotas existentes del evento.
    existing = await db.execute(
        select(EventCoordinatorQuota).where(EventCoordinatorQuota.event_id == event_id)
    )
    for q in existing.scalars().all():
        await db.delete(q)
    await db.flush()

    summary = []
    for q in quotas_data:
        operator_id = q.get("operator_id") if isinstance(q, dict) else q.operator_id
        quota = q.get("quota") if isinstance(q, dict) else q.quota
        # Resolver al objeto Operator (acepta user_id u operator_id).
        operator = await _resolve_coordinator(db, operator_id)
        if not operator:
            continue  # operador inválido, se omite
        u_result = await db.execute(select(User).where(User.id == operator.user_id))
        user = u_result.scalar_one_or_none()
        name = f"{user.first_name} {user.last_name}".upper() if user else None
        if not name:
            continue
        ecq = EventCoordinatorQuota(
            event_id=event_id,
            coordinator_operator_id=operator.id,  # FK siempre a operators.id
            coordinator=name,
            quota=int(quota),
        )
        db.add(ecq)
        summary.append({"operator_id": str(operator.id), "coordinator": name, "quota": int(quota)})
    return summary


async def _count_used_by_coordinator(
    db: AsyncSession, event_id: uuid.UUID, operator_id: uuid.UUID,
) -> int:
    """Cuenta cuántos operadores admitió este coordinador en el evento."""
    result = await db.execute(
        select(func.count()).select_from(EventAssignment)
        .where(
            EventAssignment.event_id == event_id,
            EventAssignment.admitted_by_operator_id == operator_id,
        )
    )
    return int(result.scalar() or 0)


async def create_event(db: AsyncSession, data: EventCreate, user_id: uuid.UUID) -> Event:
    """Create event with staff needs."""
    event = Event(
        name=data.name,
        description=data.description,
        location=data.location,
        address=data.address,
        city=data.city,
        start_date=data.start_date,
        end_date=data.end_date,
        setup_date=data.setup_date,
        client_name=data.client_name,
        client_phone=data.client_phone,
        notes=data.notes,
        created_by=user_id,
        status="draft",
    )
    db.add(event)
    await db.flush()

    staff_summary = []
    for need in data.staff_needs:
        sn = EventStaffNeed(
            event_id=event.id,
            role_id=need.role_id,
            quantity_needed=need.quantity_needed,
            rate_per_shift=need.rate_per_shift,
            education_level=need.education_level,
        )
        db.add(sn)
        staff_summary.append({"role_id": str(need.role_id), "qty": need.quantity_needed, "education_level": need.education_level})

    # Coordinator quotas (nuevo flujo)
    quota_summary = []
    if data.coordinator_quotas:
        quota_summary = await _save_coordinator_quotas(db, event.id, data.coordinator_quotas)

    # Audit log
    await _add_audit_log(db, event.id, user_id, "created", {
        "name": data.name, "location": data.location, "city": data.city,
        "staff_needs": staff_summary,
        "coordinator_quotas": quota_summary,
    })

    await db.commit()
    await db.refresh(event)
    return event


async def update_event(db: AsyncSession, event_id: uuid.UUID, data: EventUpdate,
                       user_id: uuid.UUID = None) -> Optional[Event]:
    """Update event fields including staff needs. Registers audit log."""
    event = await db.get(Event, event_id)
    if not event:
        return None

    # Capture old values for audit
    old_status = event.status
    old_values = {
        "name": event.name, "location": event.location, "address": event.address,
        "city": event.city, "start_date": str(event.start_date),
        "end_date": str(event.end_date), "client_name": event.client_name,
        "client_phone": event.client_phone, "description": event.description,
        "notes": event.notes, "status": event.status,
    }

    update_data = data.model_dump(exclude_unset=True)

    # Handle staff_needs and coordinator_quotas separately
    staff_needs_data = update_data.pop('staff_needs', None)
    coordinator_quotas_data = update_data.pop('coordinator_quotas', None)

    # Track changed fields (normalize datetimes to avoid false positives)
    changed_fields = {}
    for key, value in update_data.items():
        old_val = old_values.get(key)
        # Normalize datetime comparison
        if key in ('start_date', 'end_date', 'setup_date'):
            try:
                old_dt = datetime.fromisoformat(str(old_val).replace('Z', '+00:00'))
                new_dt = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
                # Strip tzinfo from both to compare naive datetimes
                old_naive = old_dt.replace(tzinfo=None)
                new_naive = new_dt.replace(tzinfo=None)
                if old_naive != new_naive:
                    changed_fields[key] = {"antes": str(old_val), "despues": str(value)}
                continue
            except (ValueError, TypeError):
                pass
        if str(old_val) != str(value):
            changed_fields[key] = {"antes": old_val, "despues": value}
        setattr(event, key, value)

    # Determine action type
    if 'status' in update_data and update_data['status'] != old_status:
        action = "status_changed"
    elif staff_needs_data is not None:
        action = "staff_updated"
    elif changed_fields:
        action = "updated"
    else:
        action = "updated"

    # Update staff needs if provided
    if staff_needs_data is not None:
        # Get old staff for audit (with role names)
        result = await db.execute(
            select(EventStaffNeed).where(EventStaffNeed.event_id == event_id)
        )
        existing = result.scalars().all()
        old_staff = []
        for sn in existing:
            role_r = await db.execute(select(Role).where(Role.id == sn.role_id))
            r = role_r.scalar_one_or_none()
            old_staff.append({
                "role_id": str(sn.role_id),
                "role_name": r.name if r else "Desconocido",
                "qty": sn.quantity_needed,
                "rate": sn.rate_per_shift,
                "education_level": sn.education_level,
            })
        for sn in existing:
            await db.delete(sn)
        await db.flush()

        new_staff = []
        for need in staff_needs_data:
            role_r = await db.execute(select(Role).where(Role.id == need['role_id']))
            r = role_r.scalar_one_or_none()
            sn = EventStaffNeed(
                event_id=event_id,
                role_id=need['role_id'],
                quantity_needed=need['quantity_needed'],
                rate_per_shift=need.get('rate_per_shift'),
                education_level=need.get('education_level'),
            )
            db.add(sn)
            new_staff.append({
                "role_id": str(need['role_id']),
                "role_name": r.name if r else "Desconocido",
                "qty": need['quantity_needed'],
                "rate": need.get('rate_per_shift'),
                "education_level": need.get('education_level'),
            })

        changed_fields["staff_needs"] = {"antes": old_staff, "despues": new_staff}

    # Update coordinator quotas if provided (nuevo flujo)
    if coordinator_quotas_data is not None:
        old_quotas_r = await db.execute(
            select(EventCoordinatorQuota).where(EventCoordinatorQuota.event_id == event_id)
        )
        old_quotas = []
        for q in old_quotas_r.scalars().all():
            name = await _resolve_coordinator_name(db, q.coordinator_operator_id) if q.coordinator_operator_id else q.coordinator
            old_quotas.append({"coordinator": name or q.coordinator, "quota": q.quota})
        new_quotas = await _save_coordinator_quotas(db, event_id, coordinator_quotas_data)
        changed_fields["coordinator_quotas"] = {"antes": old_quotas, "despues": new_quotas}
        if action == "updated" and not changed_fields.get("staff_needs"):
            action = "staff_updated"

    # Audit log
    if user_id and changed_fields:
        await _add_audit_log(db, event_id, user_id, action, changed_fields)

    await db.commit()
    await db.refresh(event)
    return event


async def get_audit_logs(db: AsyncSession, event_id: uuid.UUID, limit: int = 50) -> List[dict]:
    """Get audit logs for an event."""
    result = await db.execute(
        select(EventAuditLog)
        .where(EventAuditLog.event_id == event_id)
        .order_by(EventAuditLog.created_at.desc())
        .limit(limit)
    )
    logs = result.scalars().all()

    items = []
    for log in logs:
        changes = None
        if log.changes:
            try:
                changes = json.loads(log.changes)
            except (json.JSONDecodeError, TypeError):
                changes = log.changes
        items.append({
            "id": str(log.id),
            "action": log.action,
            "user_name": log.user_name or "Sistema",
            "changes": changes,
            "created_at": log.created_at.isoformat() if log.created_at else None,
        })
    return items


async def get_event(db: AsyncSession, event_id: uuid.UUID) -> Optional[dict]:
    """Get event with staff needs and computed totals. Auto-updates status based on dates."""
    result = await db.execute(
        select(Event)
        .options(selectinload(Event.staff_needs).selectinload(EventStaffNeed.role))
        .where(Event.id == event_id)
    )
    event = result.scalar_one_or_none()
    if not event:
        return None

    # Auto-update status based on dates (using Colombia timezone)
    now = datetime.now(COLOMBIA_TZ)
    start = event.start_date.astimezone(COLOMBIA_TZ) if event.start_date.tzinfo else event.start_date.replace(tzinfo=COLOMBIA_TZ)
    end = event.end_date.astimezone(COLOMBIA_TZ) if event.end_date.tzinfo else event.end_date.replace(tzinfo=COLOMBIA_TZ)
    status_changed = False
    if event.status == 'published' and start <= now:
        event.status = 'in_progress'
        status_changed = True
    elif event.status == 'in_progress' and end <= now:
        event.status = 'completed'
        status_changed = True
    if status_changed:
        await db.commit()
        await db.refresh(event)

    total_needed = sum(sn.quantity_needed for sn in event.staff_needs)
    total_confirmed = sum(sn.quantity_confirmed for sn in event.staff_needs)

    staff_needs = []
    for sn in event.staff_needs:
        staff_needs.append({
            "id": sn.id,
            "role_id": sn.role_id,
            "role_name": sn.role.name if sn.role else None,
            "quantity_needed": sn.quantity_needed,
            "quantity_confirmed": sn.quantity_confirmed,
            "rate_per_shift": sn.rate_per_shift,
            "education_level": sn.education_level,
        })

    # Coordinator quotas con conteo used/available (nuevo flujo).
    coord_quotas_r = await db.execute(
        select(EventCoordinatorQuota).where(EventCoordinatorQuota.event_id == event_id)
    )
    coordinator_quotas = []
    for q in coord_quotas_r.scalars().all():
        used = 0
        if q.coordinator_operator_id:
            used = await _count_used_by_coordinator(db, event_id, q.coordinator_operator_id)
        available = (q.quota - used) if q.coordinator_operator_id else None
        coordinator_quotas.append({
            "id": q.id,
            "event_id": event_id,
            "coordinator_operator_id": q.coordinator_operator_id,
            "coordinator": q.coordinator,
            "quota": q.quota,
            "used": used,
            "available": available,
        })

    return {
        "id": event.id,
        "name": event.name,
        "slug": event.slug,
        "description": event.description,
        "location": event.location,
        "address": event.address,
        "city": event.city,
        "start_date": event.start_date,
        "end_date": event.end_date,
        "setup_date": event.setup_date,
        "status": event.status,
        "created_by": event.created_by,
        "client_name": event.client_name,
        "client_phone": event.client_phone,
        "notes": event.notes,
        "staff_needs": staff_needs,
        "coordinator_quotas": coordinator_quotas,
        "total_staff_needed": total_needed,
        "total_confirmed": total_confirmed,
        "created_at": event.created_at,
    }


async def list_events(
    db: AsyncSession, status: Optional[str] = None, limit: int = 20, offset: int = 0
) -> tuple[List[dict], int]:
    """List events with filters."""
    query = select(Event).options(selectinload(Event.staff_needs))
    count_query = select(func.count()).select_from(Event)

    if status:
        query = query.where(Event.status == status)
        count_query = count_query.where(Event.status == status)

    query = query.order_by(Event.created_at.desc()).limit(limit).offset(offset)
    total = (await db.execute(count_query)).scalar()
    result = await db.execute(query)
    events = result.scalars().all()

    items = []
    now = datetime.now(COLOMBIA_TZ)
    status_updates = []
    for e in events:
        # Auto-correct status based on dates
        start = e.start_date.astimezone(COLOMBIA_TZ) if e.start_date.tzinfo else e.start_date.replace(tzinfo=COLOMBIA_TZ)
        end = e.end_date.astimezone(COLOMBIA_TZ) if e.end_date.tzinfo else e.end_date.replace(tzinfo=COLOMBIA_TZ)
        if e.status == 'in_progress' and start > now:
            e.status = 'published'
            status_updates.append(e)
        elif e.status == 'published' and start <= now and end > now:
            e.status = 'in_progress'
            status_updates.append(e)
        elif e.status == 'in_progress' and end <= now:
            e.status = 'completed'
            status_updates.append(e)

        total_needed = sum(sn.quantity_needed for sn in e.staff_needs)
        total_confirmed = sum(sn.quantity_confirmed for sn in e.staff_needs)
        items.append({
            "id": e.id,
            "name": e.name,
            "slug": e.slug,
            "description": e.description,
            "location": e.location,
            "address": e.address,
            "city": e.city,
            "start_date": e.start_date,
            "end_date": e.end_date,
            "setup_date": e.setup_date,
            "status": e.status,
            "created_by": e.created_by,
            "client_name": e.client_name,
            "client_phone": e.client_phone,
            "notes": e.notes,
            "staff_needs": [],
            "total_staff_needed": total_needed,
            "total_confirmed": total_confirmed,
            "created_at": e.created_at,
        })
    if status_updates:
        await db.commit()
    return items, total


async def assign_operators(
    db: AsyncSession, event_id: uuid.UUID, operator_ids: List[uuid.UUID],
    role_id: Optional[uuid.UUID] = None, rate: Optional[float] = None,
    programmed_by_operator_id: Optional[uuid.UUID] = None,
) -> List[EventAssignment]:
    """Assign operators to an event. operator_ids can be user_ids or operator_ids.
    If no rate is provided, uses the rate_per_shift from EventStaffNeed for the role.

    programmed_by_operator_id (nuevo flujo): operador-coordinador que
    programa/admite a estos operadores. Si se provee, se estampan las FKs
    programmed_by_operator_id / admitted_by_operator_id y los strings
    programmed_by / admitted_by (nombre en MAYÚSCULAS del coordinador).
    El cupo es informativo: nunca bloquea la asignación.
    """
    # Resolver coordinador (si vino el nuevo flujo): objeto Operator + nombre.
    coord_operator: Optional[Operator] = None
    coord_name: Optional[str] = None
    if programmed_by_operator_id:
        coord_operator = await _resolve_coordinator(db, programmed_by_operator_id)
        if coord_operator:
            coord_name = await _resolve_coordinator_name(db, programmed_by_operator_id)
    # Auto-fill rate from EventStaffNeed if not provided
    if not rate and role_id:
        sn_result = await db.execute(
            select(EventStaffNeed).where(
                EventStaffNeed.event_id == event_id,
                EventStaffNeed.role_id == role_id,
            )
        )
        staff_need = sn_result.scalar_one_or_none()
        if staff_need and staff_need.rate_per_shift:
            rate = staff_need.rate_per_shift

    # Get current event dates for overlap check
    current_event = await db.get(Event, event_id)
    if not current_event:
        return []

    assignments = []
    unavailable = []
    for uid in operator_ids:
        # Resolve: could be user_id or operator_id
        op_result = await db.execute(
            select(Operator).where(
                (Operator.id == uid) | (Operator.user_id == uid)
            )
        )
        operator = op_result.scalar_one_or_none()
        if not operator:
            continue

        # Check not already assigned to THIS event
        existing = await db.execute(
            select(EventAssignment).where(
                EventAssignment.event_id == event_id,
                EventAssignment.operator_id == operator.id,
            )
        )
        if existing.scalar_one_or_none():
            continue

        # Check for overlapping events (double-booking)
        overlap_result = await db.execute(
            select(EventAssignment)
            .join(Event, EventAssignment.event_id == Event.id)
            .where(
                EventAssignment.operator_id == operator.id,
                EventAssignment.status.in_(["invited", "confirmed", "checked_in", "standby"]),
                EventAssignment.event_id != event_id,
                Event.status.in_(["draft", "published", "in_progress"]),
                Event.start_date < current_event.end_date,
                Event.end_date > current_event.start_date,
            )
        )
        overlap = overlap_result.scalars().first()
        if overlap:
            # Get overlapping event name for error message
            overlap_event = await db.get(Event, overlap.event_id)
            unavailable.append({
                "operator_id": str(operator.id),
                "user_id": str(operator.user_id),
                "conflict_event": overlap_event.name if overlap_event else "Evento desconocido",
                "conflict_event_id": str(overlap.event_id),
            })
            continue
        assignment_kwargs = dict(
            event_id=event_id,
            operator_id=operator.id,
            role_id=role_id,
            status="invited",
            invited_at=datetime.now(timezone.utc),
            rate_applied=rate,
        )
        # Estampar coordinador (nuevo flujo) si se proveyó y resolvió.
        if coord_operator:
            assignment_kwargs["programmed_by_operator_id"] = coord_operator.id
            assignment_kwargs["admitted_by_operator_id"] = coord_operator.id
            if coord_name:
                assignment_kwargs["programmed_by"] = coord_name
                assignment_kwargs["admitted_by"] = coord_name
        assignment = EventAssignment(**assignment_kwargs)
        db.add(assignment)
        assignments.append(assignment)

    await db.commit()
    if unavailable:
        # Return assignments but also signal unavailable operators
        return assignments, unavailable
    return assignments, []


async def get_assignments(db: AsyncSession, event_id: uuid.UUID) -> List[dict]:
    """Get all assignments for an event.

    Usa un solo query con JOINs (evita el problema N+1: antes ejecutaba
    3 queries por asignacion; ahora 1 query total).
    """
    result = await db.execute(
        select(EventAssignment, Operator, User, Role)
        .join(Operator, Operator.id == EventAssignment.operator_id)
        .join(User, User.id == Operator.user_id)
        .outerjoin(Role, Role.id == EventAssignment.role_id)
        .where(EventAssignment.event_id == event_id)
        .order_by(EventAssignment.status, EventAssignment.invited_at)
    )

    items = []
    for a, op, user, role in result.all():
        items.append({
            "id": a.id,
            "event_id": a.event_id,
            "operator_id": a.operator_id,
            "operator_user_id": str(op.user_id) if op else None,
            "role_id": a.role_id,
            "role_name": role.name if role else None,
            "operator_name": f"{user.first_name} {user.last_name}" if user else "N/A",
            "operator_phone": user.phone if user else None,
            "status": a.status,
            "invited_at": a.invited_at,
            "confirmed_at": a.confirmed_at,
            "rate_applied": a.rate_applied,
            "operator_first_name": user.first_name if user else None,
            "operator_last_name": user.last_name if user else None,
            "operator_document_number": user.document_number if user else None,
            "shirt_number": a.shirt_number,
            "jacket_number": a.jacket_number,
            "cap_number": a.cap_number,
        })
    return items


async def list_available_operators(
    db: AsyncSession, event_id: uuid.UUID
) -> List[dict]:
    """Lista operadores disponibles para asignar a un evento.

    - Excluye los ya asignados al evento.
    - Marca los que tienen solapamiento con otro evento en las mismas fechas.
    """
    current_event = await db.get(Event, event_id)
    if not current_event:
        return []

    # Operadores ya asignados a este evento (para excluirlos).
    assigned_r = await db.execute(
        select(EventAssignment.operator_id).where(EventAssignment.event_id == event_id)
    )
    assigned_ids = {row[0] for row in assigned_r.all()}

    # Todos los operadores activos.
    result = await db.execute(
        select(Operator, User)
        .join(User, User.id == Operator.user_id)
        .where(Operator.is_active == True)
        .order_by(User.first_name, User.last_name)
    )

    out = []
    for op, u in result.all():
        if op.id in assigned_ids:
            continue
        # Verificar solapamiento con otros eventos.
        overlap_r = await db.execute(
            select(EventAssignment)
            .join(Event, EventAssignment.event_id == Event.id)
            .where(
                EventAssignment.operator_id == op.id,
                EventAssignment.status.in_(["invited", "confirmed", "checked_in", "standby"]),
                Event.status.in_(["draft", "published", "in_progress"]),
                Event.start_date < current_event.end_date,
                Event.end_date > current_event.start_date,
            )
        )
        overlap = overlap_r.scalars().first()
        out.append({
            "operator_id": str(op.id),
            "user_id": str(op.user_id),
            "name": f"{u.first_name} {u.last_name}",
            "document_number": u.document_number,
            "phone": u.phone,
            "available": overlap is None,
            "conflict_event_id": str(overlap.event_id) if overlap else None,
        })
    return out


async def delete_event(db: AsyncSession, event_id: uuid.UUID) -> bool:
    """Soft delete an event."""
    event = await db.get(Event, event_id)
    if not event:
        return False
    await db.delete(event)
    await db.commit()
    return True
