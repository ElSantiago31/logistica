"""Event service - CRUD and assignment logic."""
import uuid
from datetime import datetime, timezone
from typing import Optional, List

from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.events import Event, EventStaffNeed, EventAssignment
from app.models.operators import Operator
from app.models.roles import Role
from app.models.users import User
from app.schemas.events import EventCreate, EventUpdate


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

    for need in data.staff_needs:
        sn = EventStaffNeed(
            event_id=event.id,
            role_id=need.role_id,
            quantity_needed=need.quantity_needed,
            rate_per_shift=need.rate_per_shift,
        )
        db.add(sn)

    await db.commit()
    await db.refresh(event)
    return event


async def update_event(db: AsyncSession, event_id: uuid.UUID, data: EventUpdate) -> Optional[Event]:
    """Update event fields."""
    event = await db.get(Event, event_id)
    if not event:
        return None
    update_data = data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(event, key, value)
    await db.commit()
    await db.refresh(event)
    return event


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

    # Auto-update status based on dates
    now = datetime.now(timezone.utc)
    status_changed = False
    if event.status == 'published' and event.start_date <= now:
        event.status = 'in_progress'
        status_changed = True
    elif event.status == 'in_progress' and event.end_date <= now:
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

    query = query.order_by(Event.start_date.desc()).limit(limit).offset(offset)
    total = (await db.execute(count_query)).scalar()
    result = await db.execute(query)
    events = result.scalars().all()

    items = []
    for e in events:
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
    return items, total


async def assign_operators(
    db: AsyncSession, event_id: uuid.UUID, operator_ids: List[uuid.UUID],
    role_id: Optional[uuid.UUID] = None, rate: Optional[float] = None,
) -> List[EventAssignment]:
    """Assign operators to an event. operator_ids can be user_ids or operator_ids.
    If no rate is provided, uses the rate_per_shift from EventStaffNeed for the role."""
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
        assignment = EventAssignment(
            event_id=event_id,
            operator_id=operator.id,
            role_id=role_id,
            status="invited",
            invited_at=datetime.now(timezone.utc),
            rate_applied=rate,
        )
        db.add(assignment)
        assignments.append(assignment)

    await db.commit()
    if unavailable:
        # Return assignments but also signal unavailable operators
        return assignments, unavailable
    return assignments, []


async def get_assignments(db: AsyncSession, event_id: uuid.UUID) -> List[dict]:
    """Get all assignments for an event."""
    result = await db.execute(
        select(EventAssignment)
        .where(EventAssignment.event_id == event_id)
        .order_by(EventAssignment.status, EventAssignment.invited_at)
    )
    assignments = result.scalars().all()

    items = []
    for a in assignments:
        # Get operator info
        op_result = await db.execute(
            select(Operator).where(Operator.id == a.operator_id)
        )
        op = op_result.scalar_one_or_none()
        user = None
        if op:
            user_result = await db.execute(select(User).where(User.id == op.user_id))
            user = user_result.scalar_one_or_none()

        role_name = None
        if a.role_id:
            role_result = await db.execute(select(Role).where(Role.id == a.role_id))
            role = role_result.scalar_one_or_none()
            role_name = role.name if role else None

        items.append({
            "id": a.id,
            "event_id": a.event_id,
            "operator_id": a.operator_id,
            "operator_user_id": str(op.user_id) if op else None,
            "role_id": a.role_id,
            "role_name": role_name,
            "operator_name": f"{user.first_name} {user.last_name}" if user else "N/A",
            "operator_phone": user.phone if user else None,
            "status": a.status,
            "invited_at": a.invited_at,
            "confirmed_at": a.confirmed_at,
            "rate_applied": a.rate_applied,
        })
    return items


async def delete_event(db: AsyncSession, event_id: uuid.UUID) -> bool:
    """Soft delete an event."""
    event = await db.get(Event, event_id)
    if not event:
        return False
    await db.delete(event)
    await db.commit()
    return True