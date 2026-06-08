"""Event router - API endpoints for event management."""
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies.auth import get_current_user
from app.models.users import User
from app.schemas.events import (
    EventCreate, EventUpdate, EventResponse, EventListResponse,
    AssignmentResponse, AssignOperatorsRequest,
)
from app.services import events as svc

router = APIRouter(prefix="/api/events", tags=["events"])


@router.post("/", response_model=EventResponse, status_code=201)
async def create_event(
    data: EventCreate,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """Create a new event with staff needs."""
    if user.user_type not in ("superadmin", "coordinator"):
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
    if user.user_type not in ("superadmin", "coordinator"):
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
    if user.user_type not in ("superadmin", "coordinator"):
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
    if user.user_type not in ("superadmin", "coordinator"):
        raise HTTPException(403, "Sin permisos")
    event = await svc.update_event(db, event_id, data)
    if not event:
        raise HTTPException(404, "Evento no encontrado")
    result = await svc.get_event(db, event_id)
    return result


@router.delete("/{event_id}")
async def delete_event(
    event_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """Delete an event."""
    if user.user_type not in ("superadmin", "coordinator"):
        raise HTTPException(403, "Sin permisos")
    ok = await svc.delete_event(db, event_id)
    if not ok:
        raise HTTPException(404, "Evento no encontrado")
    return {"message": "Evento eliminado"}


@router.post("/{event_id}/assign")
async def assign_operators(
    event_id: uuid.UUID,
    data: AssignOperatorsRequest,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """Assign operators to an event."""
    if user.user_type not in ("superadmin", "coordinator"):
        raise HTTPException(403, "Sin permisos")
    # Verify event exists
    event = await svc.get_event(db, event_id)
    if not event:
        raise HTTPException(404, "Evento no encontrado")
    assignments, unavailable = await svc.assign_operators(
        db, event_id, data.operator_ids, data.role_id, data.rate_applied
    )
    # Return updated assignments + any conflicts
    all_assignments = await svc.get_assignments(db, event_id)
    result = {"assignments": all_assignments, "unavailable": unavailable}
    return result


@router.post("/{event_id}/check-availability")
async def check_availability(
    event_id: uuid.UUID,
    data: AssignOperatorsRequest,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """Check which operators are available for an event (no double-booking)."""
    if user.user_type not in ("superadmin", "coordinator"):
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


@router.get("/{event_id}/assignments", response_model=list[AssignmentResponse])
async def get_assignments(
    event_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """Get all assignments for an event."""
    if user.user_type not in ("superadmin", "coordinator"):
        raise HTTPException(403, "Sin permisos")
    return await svc.get_assignments(db, event_id)
