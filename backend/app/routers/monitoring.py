"""Monitoring router — API read-only para la vista 360 de gerencia.

Solo lectura: nadie puede modificar nada desde aquí. Guard central:
`permissions.can_view_monitoring` (gerencia | superadmin | admin).
"""
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.templating import Jinja2Templates
from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app import permissions
from app.database import get_db
from app.dependencies.auth import get_current_active_user
from app.models.events import Event, EventAssignment, EventStaffNeed
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
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    """Lista paginada de eventos con avance global de check-in."""
    _require_monitoring(user)

    # Total de eventos para calcular páginas
    total = (await db.execute(select(func.count()).select_from(Event))).scalar() or 0
    total_pages = max((total + page_size - 1) // page_size, 1)

    confirmed_case = case(
        (EventAssignment.status == "confirmed", 1), else_=0,
    )
    checked_case = case(
        (EventAssignment.status == "checked_in", 1), else_=0,
    )
    # Personal REQUERIDO por evento (plan de personal). Subquery escalar para
    # no romper el GROUP BY de asignaciones (evita producto cartesiano).
    required_subq = (
        select(func.coalesce(func.sum(EventStaffNeed.quantity_needed), 0))
        .where(EventStaffNeed.event_id == Event.id)
        .correlate(Event)
        .scalar_subquery()
    )
    result = await db.execute(
        select(
            Event,
            func.sum(confirmed_case).label("confirmed"),
            func.sum(checked_case).label("checked_in"),
            required_subq.label("required"),
        )
        .outerjoin(EventAssignment, EventAssignment.event_id == Event.id)
        .group_by(Event.id)
        .order_by(Event.start_date.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    rows = result.all()

    return {
        "items": [
            {
                "id": str(ev.id),
                "name": ev.name,
                "status": ev.status,
                "start_date": ev.start_date.isoformat() if ev.start_date else None,
                "location": ev.location,
                "confirmed": int(conf or 0),
                "checked_in": int(chk or 0),
                "required": int(req or 0),
            }
            for ev, conf, chk, req in rows
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": total_pages,
    }


@router.get("/events/{event_id}/overview")
async def event_overview(
    event_id: uuid.UUID,
    stage: str = Query(None, description="Filtrar por etapa: previa|avanzada|evento|desmontaje"),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_active_user),
):
    """Resumen 360 del evento: totales, roles, coordinadores, etapas y feed.

    Con ?stage= se filtran totales, roles, coordinadores y feed a la etapa
    (los anillos globales cambian según la etapa seleccionada).
    """
    _require_monitoring(user)

    ev = (await db.execute(
        select(Event).where(Event.id == event_id)
    )).scalar_one_or_none()
    if not ev:
        raise HTTPException(404, "Evento no encontrado")

    # --- Etapas presentes en el evento (plan de personal + asignaciones) ---
    stage_rows = (await db.execute(
        select(EventStaffNeed.stage)
        .where(EventStaffNeed.event_id == event_id)
        .distinct()
    )).scalars().all()
    assign_stages = (await db.execute(
        select(EventAssignment.stage)
        .where(EventAssignment.event_id == event_id)
        .distinct()
    )).scalars().all()
    stages = sorted({(s or "evento") for s in list(stage_rows) + list(assign_stages)})

    # --- Totales por estado (una query agrupada, filtrable por etapa) ---
    status_q = (
        select(EventAssignment.status, func.count(EventAssignment.id))
        .where(EventAssignment.event_id == event_id)
        .group_by(EventAssignment.status)
    )
    if stage:
        status_q = status_q.where(EventAssignment.stage == stage)
    status_rows = (await db.execute(status_q)).all()
    by_status = {s: int(c) for s, c in status_rows}

    assigned = sum(by_status.values())
    confirmed = by_status.get("confirmed", 0)
    checked_in = by_status.get("checked_in", 0)

    # Personal REQUERIDO segun el plan de personal (EventStaffNeed).
    required_q = select(
        func.coalesce(func.sum(EventStaffNeed.quantity_needed), 0)
    ).where(EventStaffNeed.event_id == event_id)
    if stage:
        required_q = required_q.where(EventStaffNeed.stage == stage)
    required = int((await db.execute(required_q)).scalar() or 0)

    # Denominador del check-in global: personal REQUERIDO (plan de personal),
    # no los invitados/asignados. Fallback si el evento no tiene plan:
    # confirmed + checked_in (los checked_in no siempre pasan por "confirmed"
    # por admisión directa del coordinador, asi que se suman ambos).
    checkin_denom = required if required > 0 else (confirmed + checked_in)

    totals = {
        "assigned": assigned,
        "invited": by_status.get("invited", 0),
        "confirmed": confirmed,
        "checked_in": checked_in,
        "required": required,
        "no_show": by_status.get("no_show", 0),
        "rejected": by_status.get("rejected", 0),
        "standby": by_status.get("standby", 0),
        "pending_checkin": max(confirmed, 0),
        "checkin_pct": round(checked_in / checkin_denom * 100, 1) if checkin_denom else 0,
    }

    # --- Por rol: helper de sync + confirmados por rol (merge) ---
    needs = await _get_event_staff_needs(db, event_id, stage=stage)
    confirmed_q = select(
        EventAssignment.role_id, func.count(EventAssignment.id)
    ).where(
        EventAssignment.event_id == event_id,
        EventAssignment.status == "confirmed",
        EventAssignment.role_id.isnot(None),
    ).group_by(EventAssignment.role_id)
    if stage:
        confirmed_q = confirmed_q.where(EventAssignment.stage == stage)
    confirmed_by_role = {
        str(rid): int(c) for rid, c in (await db.execute(confirmed_q)).all()
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

    # --- Por coordinador: helper de sync (filtrable por etapa) ---
    by_coordinator = await _get_coordinator_quotas(db, event_id, stage=stage)

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
    feed_q = (
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
    )
    if stage:
        feed_q = feed_q.where(EventAssignment.stage == stage)
    feed_rows = (await db.execute(feed_q)).all()
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
        "stage": stage,
        "stages": stages,
        "totals": totals,
        "by_role": by_role,
        "by_coordinator": by_coordinator,
        "by_stage": by_stage,
        "recent_checkins": recent_checkins,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }