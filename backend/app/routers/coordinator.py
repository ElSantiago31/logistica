"""Coordinator router — evaluación post-evento basada en jerarquía de roles.

Jerarquía:
  Level 1 (Coordinador General) → evalúa a Coordinadores de área (level 2)
  Level 2 (Coordinador de área)  → evalúa a Operadores (level 3) de su misma área
  Level 3 (Operador)             → solo recibe evaluaciones
"""
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, and_, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.dependencies.auth import get_current_user
from app.models.events import Event, EventAssignment, EventCoordinatorQuota
from app.models.operators import Operator
from app.models.payroll import Evaluation
from app.models.roles import Role
from app.models.users import User
from app.services import events as event_svc

router = APIRouter(prefix="/api/coordinator", tags=["Coordinator Evaluation"])


async def _get_my_coordinator_assignment(
    db: AsyncSession, event_id: uuid.UUID, user: User
) -> EventAssignment | None:
    """Obtiene la asignación del user actual en un evento donde es coordinador (level 1 o 2).
    Retorna None si no tiene asignación de coordinador confirmada.
    """
    # Obtener el operator profile del usuario
    op_result = await db.execute(
        select(Operator).where(Operator.user_id == user.id)
    )
    operator = op_result.scalar_one_or_none()
    if not operator:
        return None

    # Buscar asignación confirmada con rol de coordinador
    result = await db.execute(
        select(EventAssignment)
        .join(Role, EventAssignment.role_id == Role.id)
        .where(
            EventAssignment.event_id == event_id,
            EventAssignment.operator_id == operator.id,
            EventAssignment.status.in_(["confirmed", "checked_in"]),
            Role.hierarchy_level.in_([1, 2]),
            Role.is_active == True,
        )
    )
    return result.scalar_one_or_none()


@router.get("/my-events")
async def my_coordinator_events(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Eventos donde el usuario actual es coordinador confirmado (level 1 o 2)."""
    op_result = await db.execute(
        select(Operator).where(Operator.user_id == user.id)
    )
    operator = op_result.scalar_one_or_none()
    if not operator:
        return {"events": []}

    result = await db.execute(
        select(EventAssignment, Event, Role)
        .join(Event, EventAssignment.event_id == Event.id)
        .join(Role, EventAssignment.role_id == Role.id)
        .where(
            EventAssignment.operator_id == operator.id,
            EventAssignment.status.in_(["confirmed", "checked_in"]),
            Role.hierarchy_level.in_([1, 2]),
            Role.is_active == True,
            Event.status.in_(["in_progress", "completed"]),
        )
        .order_by(Event.start_date.desc())
    )
    rows = result.all()

    return {
        "events": [
            {
                "id": str(ev.id),
                "name": ev.name,
                "start_date": ev.start_date.isoformat() if ev.start_date else None,
                "end_date": ev.end_date.isoformat() if ev.end_date else None,
                "status": ev.status,
                "my_role": role.name,
                "my_level": role.hierarchy_level,
                "my_area": role.area,
            }
            for asn, ev, role in rows
        ]
    }


@router.get("/events/{event_id}/team")
async def get_team_to_evaluate(
    event_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Personal a evaluar según la jerarquía del coordinador actual."""
    my_assignment = await _get_my_coordinator_assignment(db, event_id, user)
    if not my_assignment:
        raise HTTPException(403, "No eres coordinador confirmado en este evento")

    # Cargar mi rol para saber nivel y área
    my_role = await db.get(Role, my_assignment.role_id)
    if not my_role:
        raise HTTPException(403, "Rol no válido")

    # Construir filtro según jerarquía
    if my_role.hierarchy_level == 1:
        # Coordinador General → evalúa a todos los level 2 del evento
        team_filter = and_(
            EventAssignment.event_id == event_id,
            EventAssignment.status.in_(["confirmed", "checked_in"]),
            Role.hierarchy_level == 2,
        )
    elif my_role.hierarchy_level == 2:
        # Coordinador de área → evalúa a level 3 de su misma área
        team_filter = and_(
            EventAssignment.event_id == event_id,
            EventAssignment.status.in_(["confirmed", "checked_in"]),
            Role.hierarchy_level == 3,
            Role.area == my_role.area,
        )
    else:
        raise HTTPException(403, "Tu rol no permite evaluar")

    # Consultar equipo a evaluar
    result = await db.execute(
        select(EventAssignment, Operator, User, Role)
        .join(Operator, EventAssignment.operator_id == Operator.id)
        .join(User, User.id == Operator.user_id)
        .join(Role, EventAssignment.role_id == Role.id)
        .where(team_filter)
        .order_by(User.first_name)
    )
    rows = result.all()

    # Consultar evaluaciones existentes del evaluador actual
    ev_result = await db.execute(
        select(Evaluation).where(
            Evaluation.event_id == event_id,
            Evaluation.evaluated_by == user.id,
        )
    )
    existing_evals = {str(e.operator_id): e for e in ev_result.scalars().all()}

    return {
        "event_id": str(event_id),
        "my_role": my_role.name,
        "my_level": my_role.hierarchy_level,
        "my_area": my_role.area,
        "team": [
            {
                "assignment_id": str(asn.id),
                "operator_id": str(op.id),
                "name": f"{u.first_name} {u.last_name}",
                "document_number": u.document_number,
                "role": role.name,
                "area": role.area,
                "level": role.hierarchy_level,
                "photo": op.photo_thumbnail_path,
                "already_evaluated": str(op.id) in existing_evals,
                "overall_score": existing_evals[str(op.id)].overall_score
                    if str(op.id) in existing_evals else None,
            }
            for asn, op, u, role in rows
        ],
    }


@router.post("/evaluations")
async def create_evaluation(
    payload: dict,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Crear evaluación post-evento de un operador/coordinador.

    Body:
        event_id, operator_id, punctuality_score (1-5), performance_score,
        appearance_score, attitude_score, comments, would_hire_again
    """
    event_id = uuid.UUID(payload["event_id"])
    target_operator_id = uuid.UUID(payload["operator_id"])

    # 1. Verificar que yo soy coordinador en este evento
    my_assignment = await _get_my_coordinator_assignment(db, event_id, user)
    if not my_assignment:
        raise HTTPException(403, "No eres coordinador confirmado en este evento")

    my_role = await db.get(Role, my_assignment.role_id)

    # 2. Verificar que el target está en el evento
    target_result = await db.execute(
        select(EventAssignment)
        .join(Role, EventAssignment.role_id == Role.id)
        .where(
            EventAssignment.event_id == event_id,
            EventAssignment.operator_id == target_operator_id,
            EventAssignment.status.in_(["confirmed", "checked_in"]),
        )
    )
    target_asn = target_result.scalar_one_or_none()
    if not target_asn:
        raise HTTPException(404, "Operador no encontrado en este evento")

    target_role = await db.get(Role, target_asn.role_id)

    # 3. Validar jerarquía
    can_eval = False
    if my_role.hierarchy_level == 1 and target_role.hierarchy_level == 2:
        can_eval = True
    elif my_role.hierarchy_level == 2 and target_role.hierarchy_level == 3:
        if my_role.area == target_role.area:
            can_eval = True

    if not can_eval:
        raise HTTPException(
            403,
            f"No puedes evaluar a este operador. Tu rol ({my_role.name}, nivel {my_role.hierarchy_level}) "
            f"no es superior jerárquico directo del target ({target_role.name}, nivel {target_role.hierarchy_level})."
        )

    # 4. Verificar que no exista ya una evaluación mía para este operador/evento
    existing = await db.execute(
        select(Evaluation).where(
            Evaluation.event_id == event_id,
            Evaluation.operator_id == target_operator_id,
            Evaluation.evaluated_by == user.id,
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(409, "Ya evaluaste a este operador en este evento")

    # 5. Crear evaluación
    scores = [
        int(payload.get("punctuality_score", 3)),
        int(payload.get("performance_score", 3)),
        int(payload.get("appearance_score", 3)),
        int(payload.get("attitude_score", 3)),
    ]
    for s in scores:
        if not (1 <= s <= 5):
            raise HTTPException(400, "Los scores deben estar entre 1 y 5")

    overall = round(sum(scores) / len(scores), 2)

    evaluation = Evaluation(
        event_id=event_id,
        operator_id=target_operator_id,
        evaluated_by=user.id,
        punctuality_score=scores[0],
        performance_score=scores[1],
        appearance_score=scores[2],
        attitude_score=scores[3],
        overall_score=overall,
        comments=payload.get("comments"),
        would_hire_again=payload.get("would_hire_again", True),
    )
    db.add(evaluation)
    await db.commit()

    return {"id": str(evaluation.id), "overall_score": overall}


@router.get("/events/{event_id}/evaluations")
async def get_my_evaluations(
    event_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Ver las evaluaciones que yo (coordinador) he hecho en este evento."""
    my_assignment = await _get_my_coordinator_assignment(db, event_id, user)
    if not my_assignment:
        raise HTTPException(403, "No eres coordinador confirmado en este evento")

    result = await db.execute(
        select(Evaluation, Operator, User)
        .join(Operator, Evaluation.operator_id == Operator.id)
        .join(User, User.id == Operator.user_id)
        .where(
            Evaluation.event_id == event_id,
            Evaluation.evaluated_by == user.id,
        )
    )
    rows = result.all()

    return {
        "event_id": str(event_id),
        "evaluations": [
            {
                "id": str(evl.id),
                "operator_name": f"{u.first_name} {u.last_name}",
                "punctuality": evl.punctuality_score,
                "performance": evl.performance_score,
                "appearance": evl.appearance_score,
                "attitude": evl.attitude_score,
                "overall": evl.overall_score,
                "would_hire": evl.would_hire_again,
                "comments": evl.comments,
            }
            for evl, op, u in rows
        ],
        "total": len(rows),
    }


# ============================================================
# GESTIÓN DE CUPOS — nuevo flujo
# ============================================================

async def _get_my_operator(db: AsyncSession, user: User) -> Operator | None:
    """Obtiene el perfil Operator del usuario actual."""
    result = await db.execute(select(Operator).where(Operator.user_id == user.id))
    return result.scalar_one_or_none()


@router.get("/my-quotas")
async def my_quotas(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Lista los eventos donde el coordinador actual tiene un cupo asignado,
    con conteo de usados/disponibles."""
    operator = await _get_my_operator(db, user)
    if not operator:
        return {"quotas": []}

    result = await db.execute(
        select(EventCoordinatorQuota, Event)
        .join(Event, EventCoordinatorQuota.event_id == Event.id)
        .where(
            EventCoordinatorQuota.coordinator_operator_id == operator.id,
            Event.is_active == True,
        )
        .order_by(Event.start_date.desc())
    )
    rows = result.all()

    out = []
    for quota, ev in rows:
        used = await event_svc._count_used_by_coordinator(db, ev.id, operator.id)
        out.append({
            "id": str(quota.id),
            "event_id": str(ev.id),
            "event_name": ev.name,
            "event_start": ev.start_date.isoformat() if ev.start_date else None,
            "event_status": ev.status,
            "quota": quota.quota,
            "used": used,
            "available": (quota.quota - used) if quota.quota is not None else None,
        })
    return {"quotas": out}


@router.get("/events/{event_id}/my-quota")
async def my_quota_for_event(
    event_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Cupo del coordinador actual para un evento específico + lista de operadores admitidos."""
    operator = await _get_my_operator(db, user)
    if not operator:
        raise HTTPException(404, "No tienes perfil de operador")

    quota_r = await db.execute(
        select(EventCoordinatorQuota).where(
            EventCoordinatorQuota.event_id == event_id,
            EventCoordinatorQuota.coordinator_operator_id == operator.id,
        )
    )
    quota = quota_r.scalar_one_or_none()
    if not quota:
        raise HTTPException(404, "No tienes cupo asignado en este evento")

    used = await event_svc._count_used_by_coordinator(db, event_id, operator.id)

    # Operadores que este coordinador admitió en este evento.
    ops_r = await db.execute(
        select(EventAssignment, Operator, User, Role)
        .join(Operator, EventAssignment.operator_id == Operator.id)
        .join(User, User.id == Operator.user_id)
        .outerjoin(Role, Role.id == EventAssignment.role_id)
        .where(
            EventAssignment.event_id == event_id,
            EventAssignment.admitted_by_operator_id == operator.id,
        )
        .order_by(EventAssignment.invited_at.desc())
    )
    admitted = []
    for a, op, u, role in ops_r.all():
        admitted.append({
            "assignment_id": str(a.id),
            "operator_id": str(op.id),
            "name": f"{u.first_name} {u.last_name}",
            "document_number": u.document_number,
            "phone": u.phone,
            "role_name": role.name if role else None,
            "status": a.status,
        })

    return {
        "event_id": str(event_id),
        "coordinator": quota.coordinator,
        "quota": quota.quota,
        "used": used,
        "available": (quota.quota - used) if quota.quota is not None else None,
        "admitted_operators": admitted,
    }


@router.post("/events/{event_id}/admit")
async def admit_operators(
    event_id: uuid.UUID,
    payload: dict,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Admite (asigna) operadores bajo el cupo del coordinador actual.

    Body: {"operator_ids": [uuid, ...], "role_id": uuid (opcional)}
    El cupo es informativo: no bloquea la asignación.
    """
    operator = await _get_my_operator(db, user)
    if not operator:
        raise HTTPException(403, "No tienes perfil de operador")

    # Validar que el coordinador tenga cupo en este evento.
    quota_r = await db.execute(
        select(EventCoordinatorQuota).where(
            EventCoordinatorQuota.event_id == event_id,
            EventCoordinatorQuota.coordinator_operator_id == operator.id,
        )
    )
    if not quota_r.scalar_one_or_none():
        raise HTTPException(403, "No tienes cupo asignado en este evento")

    # Validar IDs: filtrar valores inválidos (ej. "undefined" del frontend)
    # en lugar de lanzar un 500 genérico por ValueError.
    raw_ids = payload.get("operator_ids", []) or []
    operator_ids = []
    invalid_ids = []
    for x in raw_ids:
        try:
            operator_ids.append(uuid.UUID(str(x)))
        except (ValueError, AttributeError, TypeError):
            invalid_ids.append(str(x))
    if not operator_ids:
        raise HTTPException(
            422,
            "No se enviaron IDs de operador válidos"
            + (f" (inválidos: {invalid_ids})" if invalid_ids else ""),
        )
    role_id = None
    if payload.get("role_id"):
        try:
            role_id = uuid.UUID(str(payload["role_id"]))
        except (ValueError, AttributeError, TypeError):
            role_id = None

    assignments, unavailable = await event_svc.assign_operators(
        db, event_id, operator_ids, role_id,
        programmed_by_operator_id=operator.id,
    )

    all_assignments = await event_svc.get_assignments(db, event_id)
    return {
        "assignments": all_assignments,
        "unavailable": unavailable,
        "admitted_by": str(operator.id),
    }


@router.get("/events/{event_id}/available-operators")
async def available_operators_for_quota(
    event_id: uuid.UUID,
    search: str | None = None,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Lista operadores disponibles para asignar bajo el cupo del coordinador.

    Excluye los ya asignados al evento y aplica el filtro de solapamiento.
    Soporta búsqueda opcional por nombre/documento (query param `search`).
    """
    operator = await _get_my_operator(db, user)
    if not operator:
        raise HTTPException(403, "No tienes perfil de operador")

    # Validar cupo
    quota_r = await db.execute(
        select(EventCoordinatorQuota).where(
            EventCoordinatorQuota.event_id == event_id,
            EventCoordinatorQuota.coordinator_operator_id == operator.id,
        )
    )
    if not quota_r.scalar_one_or_none():
        raise HTTPException(403, "No tienes cupo asignado en este evento")

    operators = await event_svc.list_available_operators(db, event_id)

    # Filtro de búsqueda server-side (nombre/documento/teléfono) si se provee.
    # list_available_operators devuelve los campos: name, document_number, phone.
    if search and len(search) >= 2:
        q = search.lower().strip()
        operators = [
            o for o in operators
            if q in (
                ((o.get("name") or "")
                 + " " + (o.get("document_number") or "")
                 + " " + (o.get("phone") or "")).lower()
            )
        ]

    return {"operators": operators}
