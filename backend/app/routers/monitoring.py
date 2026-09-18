"""Monitoring router — API read-only para la vista 360 de gerencia.

Solo lectura: nadie puede modificar nada desde aquí. Guard central:
`permissions.can_view_monitoring` (gerencia | superadmin | admin).
"""
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.templating import Jinja2Templates
from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app import permissions
from app.database import get_db
from app.dependencies.auth import get_current_active_user
from app.models.events import Event, EventAssignment
from app.models.roles import Role
from app.models.sync import AttendanceLog
from app.models.operators import Operator
from app.models.users import User

# REUTILIZAR, no copiar (regla 1 del plan): las queries en vivo de roles
# requeridos y cupos por coordinador ya existen en el router de sync.
from app.routers.sync import _get_event_staff_needs, _get_coordinator_quotas

router = APIRouter(prefix="/api/monitoring", tags=["monitoring"])

page_router = APIRouter(tags=["monitoring-pages"])
templates = Jinja2Templates(directory="app/templates")


@page_router.get("/gerencia", include_in_schema=False)
async def gerencia_events_page(request: Request):
    """Lista de eventos con avance de check-in (rol gerencia)."""
    return templates.TemplateResponse("gerencia/gerencia_events.html", {"request": request})


@page_router.get("/gerencia/events/{event_id}", include_in_schema=False)
async def gerencia_monitor_page(request: Request, event_id: str):
    """Vista 360 en tiempo real de un evento (rol gerencia)."""
    return templates.TemplateResponse("gerencia/gerencia_monitor.html", {
        "request": request, "event_id": event_id,
    })


def _require_monitoring(user: User) -> None:
    if not permissions.can_view_monitoring(user):
        raise HTTPException(403, "Sin permisos para ver monitoreo")


@router.get("/events")
async def list_events_for_monitoring(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_active_user),
):
    """Lista ligera de TODOS los eventos con avance global de check-in."""
    _require_monitoring(user)

    confirmed_case = case(
        (EventAssignment.status == "confirmed", 1), else_=0,
    )
    checked_case = case(
        (EventAssignment.status == "checked_in", 1), else_=0,
    )
    result = await db.execute(
        select(
            Event,
            func.sum(confirmed_case).label("confirmed"),
            func.sum(checked_case).label("checked_in"),
        )
        .outerjoin(EventAssignment, EventAssignment.event_id == Event.id)
        .group_by(Event.id)
        .order_by(Event.start_date.desc())
    )
    rows = result.all()

    return [
        {
            "id": str(ev.id),
            "name": ev.name,
            "status": ev.status,
            "start_date": ev.start_date.isoformat() if ev.start_date else None,
            "location": ev.location,
            "confirmed": int(conf or 0),
            "checked_in": int(chk or 0),
        }
        for ev, conf, chk in rows
    ]


@router.get("/events/{event_id}/overview")
async def event_overview(
    event_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_active_user),
):
    """Resumen 360 del evento: totales, roles, coordinadores, etapas y feed."""
    _require_monitoring(user)

    ev = (await db.execute(
        select(Event).where(Event.id == event_id)
    )).scalar_one_or_none()
    if not ev:
        raise HTTPException(404, "Evento no encontrado")

    # --- Totales por estado (una query agrupada) ---
    status_rows = (await db.execute(
        select(EventAssignment.status, func.count(EventAssignment.id))
        .where(EventAssignment.event_id == event_id)
        .group_by(EventAssignment.status)
    )).all()
    by_status = {s: int(c) for s, c in status_rows}

    assigned = sum(by_status.values())
    confirmed = by_status.get("confirmed", 0)
    checked_in = by_status.get("checked_in", 0)
    totals = {
        "assigned": assigned,
        "invited": by_status.get("invited", 0),
        "confirmed": confirmed,
        "checked_in": checked_in,
        "no_show": by_status.get("no_show", 0),
        "rejected": by_status.get("rejected", 0),
        "standby": by_status.get("standby", 0),
        "pending_checkin": max(confirmed, 0),
        "checkin_pct": round(checked_in / confirmed * 100, 1) if confirmed else 0,
    }

    # --- Por rol: helper de sync + confirmados por rol (merge) ---
    needs = await _get_event_staff_needs(db, event_id)
    confirmed_by_role = {
        str(rid): int(c) for rid, c in (await db.execute(
            select(EventAssignment.role_id, func.count(EventAssignment.id))
            .where(
                EventAssignment.event_id == event_id,
                EventAssignment.status == "confirmed",
                EventAssignment.role_id.isnot(None),
            )
            .group_by(EventAssignment.role_id)
        )).all()
    }
    by_role = [
        {
            "role_name": n["role_name"],
            "needed": n["quantity_needed"],
            "confirmed": confirmed_by_role.get(n["role_id"], 0),
            "checked_in": n["checked_in"],
            "stage": n["stage"],
        }
        for n in needs
    ]

    # --- Por coordinador: helper de sync tal cual ---
    by_coordinator = await _get_coordinator_quotas(db, event_id)

    # --- Por etapa (GROUP BY stage sobre asignaciones) ---
    stage_rows = (await db.execute(
        select(
            EventAssignment.stage,
            func.count(EventAssignment.id),
            func.sum(case(
                (EventAssignment.status == "checked_in", 1), else_=0,
            )),
        )
        .where(EventAssignment.event_id == event_id)
        .group_by(EventAssignment.stage)
    )).all()
    by_stage = [
        {"stage": st or "evento", "assigned": int(c), "checked_in": int(ci or 0)}
        for st, c, ci in stage_rows
    ]

    # --- Feed: últimos 15 check-ins con nombres y rol ---
    Verifier = aliased(User)
    feed_rows = (await db.execute(
        select(AttendanceLog, Operator, User, Role, Verifier.first_name, Verifier.last_name)
        .join(Operator, Operator.id == AttendanceLog.operator_id)
        .join(User, User.id == Operator.user_id)
        .outerjoin(EventAssignment, EventAssignment.id == AttendanceLog.assignment_id)
        .outerjoin(Role, Role.id == EventAssignment.role_id)
        .outerjoin(Verifier, Verifier.id == AttendanceLog.verified_by)
        .where(
            AttendanceLog.event_id == event_id,
            AttendanceLog.check_in_time.isnot(None),
        )
        .order_by(AttendanceLog.check_in_time.desc())
        .limit(15)
    )).all()
    recent_checkins = [
        {
            "name": f"{u.first_name} {u.last_name}".strip(),
            "role_name": r.name if r else None,
            "time": att.check_in_time.isoformat() if att.check_in_time else None,
            "method": att.check_in_method,
            "by": (f"{vfn} {vln}".strip() if vfn else None),
        }
        for att, _op, u, r, vfn, vln in feed_rows
    ]

    return {
        "event": {
            "id": str(ev.id),
            "name": ev.name,
            "status": ev.status,
            "start_date": ev.start_date.isoformat() if ev.start_date else None,
            "end_date": ev.end_date.isoformat() if ev.end_date else None,
            "location": ev.location,
            "client_name": ev.client_name,
        },
        "totals": totals,
        "by_role": by_role,
        "by_coordinator": by_coordinator,
        "by_stage": by_stage,
        "recent_checkins": recent_checkins,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }