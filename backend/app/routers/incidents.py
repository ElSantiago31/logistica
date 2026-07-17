"""Incidents router — operator incidents (novedades) and bans (vetos).

Endpoints:
  - GET    /api/incidents            Lista novedades (filtros: event_id, operator_id, type)
  - POST   /api/incidents            Crea una novedad
  - DELETE /api/incidents/{id}       Elimina una novedad
  - GET    /api/bans                 Lista vetos (filtro: is_active)
  - POST   /api/bans                 Veta a un operador (ban + incident + is_banned=True)
  - POST   /api/bans/reactivate      Reactiva operador vetado (is_banned=False)
  - GET    /api/operators/{id}/ban-status  Estado de veto de un operador
"""
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies.auth import require_coordinator as require_superadmin
from app.models.incidents import OperatorIncident, OperatorBan
from app.models.operators import Operator
from app.models.events import Event
from app.models.users import User
from app.schemas.incidents import (
    IncidentCreateRequest,
    IncidentResponse,
    BanCreateRequest,
    BanReactivateRequest,
    BanResponse,
    OperatorBanStatusResponse,
)

router = APIRouter(prefix="/api/incidents", tags=["Incidents & Bans"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _resolve_operator_name(db: AsyncSession, operator_id: uuid.UUID) -> str | None:
    op = await db.get(Operator, operator_id)
    if not op:
        return None
    user = await db.get(User, op.user_id) if op.user_id else None
    if user:
        return f"{user.first_name} {user.last_name}".strip()
    return None


async def _resolve_operator_doc(db: AsyncSession, operator_id: uuid.UUID) -> str | None:
    """Resuelve el document_number del User asociado a un Operator."""
    op = await db.get(Operator, operator_id)
    if not op or not op.user_id:
        return None
    user = await db.get(User, op.user_id)
    return user.document_number if user else None


async def _resolve_user_name(db: AsyncSession, user_id: uuid.UUID | None) -> str | None:
    if not user_id:
        return None
    user = await db.get(User, user_id)
    if user:
        return f"{user.first_name} {user.last_name}".strip()
    return None


# ---------------------------------------------------------------------------
# Incidents
# ---------------------------------------------------------------------------

@router.get("", response_model=list[IncidentResponse])
async def list_incidents(
    event_id: uuid.UUID | None = Query(None),
    operator_id: uuid.UUID | None = Query(None),
    incident_type: str | None = Query(None),
    limit: int = Query(200, le=500),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_superadmin),
):
    """Lista novedades con filtros opcionales."""
    stmt = (
        select(OperatorIncident, Event, Operator, User)
        .join(Event, Event.id == OperatorIncident.event_id)
        .join(Operator, Operator.id == OperatorIncident.operator_id)
        .outerjoin(User, User.id == Operator.user_id)
        .order_by(desc(OperatorIncident.created_at))
        .limit(limit)
    )
    if event_id:
        stmt = stmt.where(OperatorIncident.event_id == event_id)
    if operator_id:
        stmt = stmt.where(OperatorIncident.operator_id == operator_id)
    if incident_type:
        stmt = stmt.where(OperatorIncident.incident_type == incident_type)

    result = await db.execute(stmt)
    rows = result.all()
    out = []
    for inc, event, op, u in rows:
        out.append(IncidentResponse(
            id=inc.id,
            event_id=inc.event_id,
            operator_id=inc.operator_id,
            recorded_by=inc.recorded_by,
            incident_type=inc.incident_type,
            description=inc.description,
            is_veto=inc.is_veto,
            created_at=inc.created_at,
            event_name=event.name,
            operator_name=f"{u.first_name} {u.last_name}".strip() if u else None,
            operator_document=u.document_number if u else None,
            recorder_name=await _resolve_user_name(db, inc.recorded_by),
        ))
    return out


@router.post("", response_model=IncidentResponse, status_code=201)
async def create_incident(
    payload: IncidentCreateRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_superadmin),
):
    """Crea una novedad."""
    # Validar existencia de evento y operador
    event = await db.get(Event, payload.event_id)
    if not event:
        raise HTTPException(404, "Evento no encontrado")
    operator = await db.get(Operator, payload.operator_id)
    if not operator:
        raise HTTPException(404, "Operador no encontrado")

    is_veto = payload.incident_type == "veto"
    inc = OperatorIncident(
        event_id=payload.event_id,
        operator_id=payload.operator_id,
        recorded_by=user.id,
        incident_type=payload.incident_type,
        description=payload.description,
        is_veto=is_veto,
    )
    db.add(inc)
    await db.commit()
    await db.refresh(inc)

    op_name = await _resolve_operator_name(db, inc.operator_id)
    op_doc = await _resolve_operator_doc(db, inc.operator_id)
    return IncidentResponse(
        id=inc.id,
        event_id=inc.event_id,
        operator_id=inc.operator_id,
        recorded_by=inc.recorded_by,
        incident_type=inc.incident_type,
        description=inc.description,
        is_veto=inc.is_veto,
        created_at=inc.created_at,
        event_name=event.name,
        operator_name=op_name,
        operator_document=op_doc,
        recorder_name=await _resolve_user_name(db, inc.recorded_by),
    )


@router.delete("/{incident_id}", status_code=204)
async def delete_incident(
    incident_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_superadmin),
):
    """Elimina una novedad."""
    inc = await db.get(OperatorIncident, incident_id)
    if not inc:
        raise HTTPException(404, "Novedad no encontrada")
    await db.delete(inc)
    await db.commit()


# ---------------------------------------------------------------------------
# Bans
# ---------------------------------------------------------------------------

@router.get("/bans", response_model=list[BanResponse])
async def list_bans(
    is_active: bool | None = Query(None),
    limit: int = Query(200, le=500),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_superadmin),
):
    """Lista vetos (opcionalmente solo activos)."""
    stmt = (
        select(OperatorBan, Operator, User)
        .join(Operator, Operator.id == OperatorBan.operator_id)
        .outerjoin(User, User.id == Operator.user_id)
        .order_by(desc(OperatorBan.created_at))
        .limit(limit)
    )
    if is_active is not None:
        stmt = stmt.where(OperatorBan.is_active == is_active)
    result = await db.execute(stmt)
    rows = result.all()
    out = []
    for ban, op, u in rows:
        out.append(BanResponse(
            id=ban.id,
            operator_id=ban.operator_id,
            banned_by=ban.banned_by,
            reason=ban.reason,
            observations=ban.observations,
            is_active=ban.is_active,
            unbanned_by=ban.unbanned_by,
            unbanned_at=ban.unbanned_at,
            unban_reason=ban.unban_reason,
            created_at=ban.created_at,
            operator_name=f"{u.first_name} {u.last_name}".strip() if u else None,
            operator_document=u.document_number if u else None,
            banner_name=await _resolve_user_name(db, ban.banned_by),
        ))
    return out


@router.post("/bans", response_model=BanResponse, status_code=201)
async def ban_operator(
    payload: BanCreateRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_superadmin),
):
    """Veta a un operador.

    Flujo:
      1. Verifica que no tenga ya un veto activo (índice único parcial lo garantiza).
      2. Crea el registro OperatorBan.
      3. Crea una novedad tipo 'veto' en el evento (si event_id viene).
      4. Actualiza Operator.is_banned = True.
    """
    operator = await db.get(Operator, payload.operator_id)
    if not operator:
        raise HTTPException(404, "Operador no encontrado")

    # Verificar veto activo existente
    existing = await db.execute(
        select(OperatorBan).where(
            OperatorBan.operator_id == payload.operator_id,
            OperatorBan.is_active == True,
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(409, "El operador ya tiene un veto activo")

    # Crear el veto
    ban = OperatorBan(
        operator_id=payload.operator_id,
        banned_by=user.id,
        reason=payload.reason,
        observations=payload.observations,
        is_active=True,
    )
    db.add(ban)

    # Snapshot en el operador
    operator.is_banned = True

    # Novedad tipo veto (si hay evento)
    if payload.event_id:
        event = await db.get(Event, payload.event_id)
        if event:
            inc = OperatorIncident(
                event_id=payload.event_id,
                operator_id=payload.operator_id,
                recorded_by=user.id,
                incident_type="veto",
                description=f"VETO: {payload.reason}",
                is_veto=True,
            )
            db.add(inc)

    await db.commit()
    await db.refresh(ban)

    op_name = await _resolve_operator_name(db, ban.operator_id)
    op_doc = await _resolve_operator_doc(db, ban.operator_id)
    return BanResponse(
        id=ban.id,
        operator_id=ban.operator_id,
        banned_by=ban.banned_by,
        reason=ban.reason,
        observations=ban.observations,
        is_active=ban.is_active,
        unbanned_by=ban.unbanned_by,
        unbanned_at=ban.unbanned_at,
        unban_reason=ban.unban_reason,
        created_at=ban.created_at,
        operator_name=op_name,
        operator_document=op_doc,
        banner_name=await _resolve_user_name(db, ban.banned_by),
    )


@router.post("/bans/reactivate", response_model=BanResponse)
async def reactivate_operator(
    payload: BanReactivateRequest,
    operator_id: uuid.UUID = Query(..., description="ID del operador a reactivar"),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_superadmin),
):
    """Reactiva a un operador vetado (quita el veto activo)."""
    result = await db.execute(
        select(OperatorBan).where(
            OperatorBan.operator_id == operator_id,
            OperatorBan.is_active == True,
        )
    )
    ban = result.scalar_one_or_none()
    if not ban:
        raise HTTPException(404, "El operador no tiene veto activo")

    ban.is_active = False
    ban.unbanned_by = user.id
    ban.unbanned_at = datetime.utcnow()
    ban.unban_reason = payload.unban_reason

    # Actualizar snapshot
    operator = await db.get(Operator, operator_id)
    if operator:
        operator.is_banned = False

    await db.commit()
    await db.refresh(ban)

    op_name = await _resolve_operator_name(db, ban.operator_id)
    op_doc = await _resolve_operator_doc(db, ban.operator_id)
    return BanResponse(
        id=ban.id,
        operator_id=ban.operator_id,
        banned_by=ban.banned_by,
        reason=ban.reason,
        observations=ban.observations,
        is_active=ban.is_active,
        unbanned_by=ban.unbanned_by,
        unbanned_at=ban.unbanned_at,
        unban_reason=ban.unban_reason,
        created_at=ban.created_at,
        operator_name=op_name,
        operator_document=op_doc,
        banner_name=await _resolve_user_name(db, ban.banned_by),
    )


@router.get("/operators/{operator_id}/ban-status", response_model=OperatorBanStatusResponse)
async def get_ban_status(
    operator_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_superadmin),
):
    """Estado de veto de un operador."""
    operator = await db.get(Operator, operator_id)
    if not operator:
        raise HTTPException(404, "Operador no encontrado")

    result = await db.execute(
        select(OperatorBan).where(
            OperatorBan.operator_id == operator_id,
            OperatorBan.is_active == True,
        )
    )
    active_ban = result.scalar_one_or_none()

    return OperatorBanStatusResponse(
        operator_id=operator_id,
        is_banned=operator.is_banned,
        active_ban=BanResponse.model_validate(active_ban) if active_ban else None,
    )