"""Incorporación Rápida: operadores "solo evento" (usuarios fantasma).

Flujo ⚡ del detalle de evento: permite al staff registrar en el mismo
detalle del evento a una persona que llegó "de última hora" sin registro
previo, creando un usuario FANTASMA:

  - user.is_active = False        → no puede iniciar sesión
  - user.email    = NULL          → no recibe correos, no colisiona
  - password aleatoria desconocida → nadie puede hacerse pasar por él
  - operator.event_only = True    → marcado para purga automática

El ghost vive únicamente mientras tenga una asignación ACTIVA en algún
evento. Cuando la última asignación se elimina (o se borra el evento),
`purge_orphan_event_only_operators` lo borra físicamente junto con su
usuario, evitando basura en el directorio de operadores.

Si el documento ya pertenece a un operador REAL registrado, no se crea
ningún ghost: se asigna el existente (mode="existing") y el admin ve la
diferencia en la respuesta.
"""
import secrets
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import HTTPException
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.events import DEFAULT_STAGE, EventAssignment, EventStaffNeed
from app.models.operators import Operator
from app.models.users import User
from app.schemas.events import QuickAddRequest, QuickAddResponse
from app.services.auth import hash_password
from app.services.operator_import import _normalize_doc_type


async def quick_add_operator(
    db: AsyncSession,
    event_id: uuid.UUID,
    payload: QuickAddRequest,
    admin_display: Optional[str] = None,
) -> QuickAddResponse:
    """Crea (o reutiliza) un operador y lo asigna confirmado al evento.

    Reglas:
      1. Documento ya registrado como operador real → asignar existente
         (mode="existing"). NUNCA se crea un ghost sobre un documento real.
      2. Documento ya registrado como ghost (event_only) de otro evento →
         reutilizar el ghost (mode="ghost").
      3. Documento nuevo → crear usuario fantasma + operador event_only
         (mode="ghost").
      4. Ya asignado a ESTE evento (etapa 'evento', activo) → 409.

    El rol/rate se toman del primer staff_need de etapa 'evento' del
    evento (si existe) para que el contador quantity_confirmed cuadre.
    """
    doc_type = _normalize_doc_type(payload.document_type)
    doc_number = payload.document_number.strip()

    # --- Buscar usuario existente por documento ---
    res = await db.execute(
        select(User).where(
            User.document_number == doc_number,
            User.document_type == doc_type,
        )
    )
    existing_user = res.scalar_one_or_none()

    mode = "ghost"
    operator: Optional[Operator] = None

    if existing_user is not None:
        # Cargar perfil de operador (si lo tiene)
        op_res = await db.execute(
            select(Operator).where(Operator.user_id == existing_user.id)
        )
        operator = op_res.scalar_one_or_none()

        if operator is not None and not operator.event_only:
            # Operador REAL registrado → asignar existente, jamás ghost.
            mode = "existing"

    # --- Verificar asignación previa en este evento (etapa evento) ---
    if operator is not None:
        dup = await db.execute(
            select(EventAssignment).where(
                EventAssignment.event_id == event_id,
                EventAssignment.operator_id == operator.id,
                EventAssignment.stage == DEFAULT_STAGE,
                EventAssignment.is_active.is_(True),
            )
        )
        if dup.scalar_one_or_none() is not None:
            raise HTTPException(
                status_code=409,
                detail=f"El documento {doc_number} ya está asignado a este evento",
            )

    # --- Rol/tarifa: primer staff_need de etapa 'evento' ---
    need_res = await db.execute(
        select(EventStaffNeed)
        .where(
            EventStaffNeed.event_id == event_id,
            EventStaffNeed.stage == DEFAULT_STAGE,
        )
        .order_by(EventStaffNeed.created_at)
        .limit(1)
    )
    need = need_res.scalar_one_or_none()
    role_id = need.role_id if need else None
    rate = need.rate_per_shift if need else None

    first_name = payload.primer_nombre.strip()
    last_name = " ".join(
        p for p in [payload.primer_apellido, payload.segundo_apellido] if p and p.strip()
    ).strip()
    if payload.segundo_nombre and payload.segundo_nombre.strip():
        first_name = f"{first_name} {payload.segundo_nombre.strip()}"

    # --- Crear ghost si aplica ---
    if operator is None:
        if existing_user is None:
            ghost_user = User(
                email=None,
                password_hash=hash_password(secrets.token_urlsafe(24)),
                first_name=first_name[:100],
                last_name=(last_name or "SIN APELLIDO")[:100],
                phone=None,
                document_type=doc_type,
                document_number=doc_number,
                user_type="operator",
                role_id=role_id,
                is_verified=False,
                is_approved=False,
                is_active=False,  # fantasma: no puede iniciar sesión
            )
            db.add(ghost_user)
            await db.flush()
            user = ghost_user
        else:
            # User sin perfil Operator (raro) → reutilizar user
            user = existing_user

        operator = Operator(
            user_id=user.id,
            event_only=True,  # ← marca de purga
        )
        db.add(operator)
        await db.flush()
    else:
        user = existing_user

    # --- Crear asignación confirmada ---
    now = datetime.now(timezone.utc)
    assignment = EventAssignment(
        event_id=event_id,
        operator_id=operator.id,
        role_id=role_id,
        rate_applied=rate,
        status="confirmed",
        stage=DEFAULT_STAGE,
        confirmed_at=now,
        is_active=True,
        reminder_sent=False,
        admitted_by=(admin_display or "QUICK-ADD")[:200],
        programmed_by="Colab A&C",
    )
    db.add(assignment)
    await db.flush()

    # --- Recalcular quantity_confirmed del staff_need usado ---
    if need is not None and role_id is not None:
        cnt = await db.execute(
            select(EventAssignment.id).where(
                EventAssignment.event_id == event_id,
                EventAssignment.role_id == role_id,
                EventAssignment.stage == DEFAULT_STAGE,
                EventAssignment.status == "confirmed",
                EventAssignment.is_active.is_(True),
            )
        )
        need.quantity_confirmed = len(cnt.all())
        await db.flush()

    await db.commit()
    await db.refresh(assignment)
    await db.refresh(operator)
    await db.refresh(user)

    role_name = None
    if role_id is not None:
        rn = await db.execute(
            text("SELECT name FROM roles WHERE id = :rid"), {"rid": str(role_id)}
        )
        row = rn.first()
        role_name = row.name if row else None

    full_name = f"{user.first_name} {user.last_name or ''}".strip()
    return QuickAddResponse(
        assignment_id=str(assignment.id),
        operator_id=str(operator.id),
        user_id=str(user.id),
        full_name=full_name,
        document_number=doc_number,
        role_id=str(role_id) if role_id else None,
        role_name=role_name,
        mode=mode,
        status="confirmed",
    )


async def purge_orphan_event_only_operators(db: AsyncSession) -> int:
    """Borra físicamente los operadores event_only sin asignaciones activas.

    Un ghost solo vive mientras tenga ≥1 asignación is_active=true. Al
    quedarse sin asignaciones (event borrado, asignación eliminada) se
    elimina junto con su usuario fantasma (is_active=false).

    Retorna la cantidad de operadores purgados. Seguro de llamar en
    cualquier momento: nunca toca operadores reales (event_only=false)
    ni usuarios activos.
    """
    res = await db.execute(text("""
        DELETE FROM operators
        WHERE event_only = true
          AND id NOT IN (
              SELECT operator_id FROM event_assignments
              WHERE is_active = true AND operator_id IS NOT NULL
          )
        RETURNING user_id
    """))
    user_ids = [str(r.user_id) for r in res.fetchall()]
    if user_ids:
        await db.execute(text(
            "DELETE FROM users WHERE id = ANY(:ids) AND is_active = false"
        ), {"ids": user_ids})
    await db.commit()
    return len(user_ids)