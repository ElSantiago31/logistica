"""Coordinator router — evaluación post-evento basada en jerarquía de roles.

Jerarquía:
  Level 1 (Coordinador General) → evalúa a Coordinadores de área (level 2)
  Level 2 (Coordinador de área)  → evalúa a Operadores (level 3) de su misma área
  Level 3 (Operador)             → solo recibe evaluaciones
"""
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.dependencies.auth import get_current_user
from app.models.events import Event, EventAssignment
from app.models.operators import Operator
from app.models.payroll import Evaluation
from app.models.roles import Role
from app.models.users import User

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