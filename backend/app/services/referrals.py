"""Referral service - business logic for the referral module.

Reglas de negocio:
- El SuperAdmin genera un código de referido (AC-NOMBRE-XXXX) por operador.
- Un referido usa el código SOLO al registrarse (público, sin login).
- La relación referido→referente es PERMANENTE (inmutable).
- Las métricas del referente son CÁLCULO DERIVADO (no contadores +1/-1):
    * total_referrals    = COUNT(referrals.referred)
    * active_referrals   = referidos con operator.is_active = True
    * assigned_referrals = referidos con >= 1 EventAssignment activa
    * worked_referrals   = referidos con >= 1 assignment status='checked_in'
"""
import json
import secrets
import string
import uuid
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.events import EventAssignment
from app.models.operators import Operator
from app.models.referrals import Referral, ReferralAuditLog, ReferralCode
from app.models.users import User

# Prefijo del código (Acompana / AC)
CODE_PREFIX = "AC"
CODE_SUFFIX_LEN = 4


class ReferralError(Exception):
    """Error de negocio del módulo de referidos."""

    def __init__(self, message: str, status_code: int = 400):
        self.message = message
        self.status_code = status_code
        super().__init__(message)


def _random_suffix(length: int = CODE_SUFFIX_LEN) -> str:
    """Sufijo aleatorio sin caracteres ambiguos (sin 0/O, 1/I/L)."""
    alphabet = string.ascii_uppercase + string.digits
    safe = "".join(c for c in alphabet if c not in "0O1IL")
    return "".join(secrets.choice(safe) for _ in range(length))


def generate_code_from_name(name: str) -> str:
    """Genera AC-NOMBRE-XXXX a partir del nombre del operador.

    Normaliza: sin acentos, solo A-Z, primera palabra significativa, máx 12 chars.
    """
    import unicodedata

    nfkd = unicodedata.normalize("NFKD", (name or "").upper())
    ascii_name = "".join(c for c in nfkd if not unicodedata.combining(c))
    words = [w for w in ascii_name.split() if w.isalpha()]
    base = words[0] if words else "REF"
    base = base[:12]
    return f"{CODE_PREFIX}-{base}-{_random_suffix()}"


async def _log(
    db: AsyncSession,
    action: str,
    *,
    referrer_operator_id: uuid.UUID | None = None,
    referred_operator_id: uuid.UUID | None = None,
    user_id: uuid.UUID | None = None,
    detail: dict | None = None,
) -> None:
    """Registra una entrada de auditoría (best-effort)."""
    log = ReferralAuditLog(
        action=action,
        referrer_operator_id=referrer_operator_id,
        referred_operator_id=referred_operator_id,
        user_id=user_id,
        detail=json.dumps(detail, default=str) if detail else None,
    )
    db.add(log)


async def create_code_for_operator(
    db: AsyncSession, operator_id: uuid.UUID, created_by: uuid.UUID
) -> ReferralCode:
    """Crea (o regenera) el código de referido de un operador.

    - Si ya existe un código ACTIVO → error (no duplicar).
    - Si existe INACTIVO → se regenera uno nuevo con sufijo distinto.
    """
    operator = await db.get(Operator, operator_id)
    if not operator:
        raise ReferralError("Operador no encontrado", 404)
    if not operator.is_active:
        raise ReferralError("No se puede generar código para un operador inactivo", 400)

    existing = await db.scalar(
        select(ReferralCode).where(ReferralCode.operator_id == operator_id)
    )
    if existing and existing.is_active:
        raise ReferralError("El operador ya tiene un código activo", 409)

    user = await db.get(User, operator.user_id) if operator.user_id else None
    name = f"{user.first_name} {user.last_name}".strip() if user else ""
    if not name:
        name = f"OP-{str(operator_id)[:8].upper()}"
    code_str = generate_code_from_name(name)
    # Garantizar unicidad del código
    for _ in range(5):
        clash = await db.scalar(select(ReferralCode).where(ReferralCode.code == code_str))
        if not clash:
            break
        code_str = generate_code_from_name(name)
    else:
        raise ReferralError("No se pudo generar un código único, intenta de nuevo", 500)

    if existing:
        # Regenerar: mismo registro, nuevo código, se re-activa
        existing.code = code_str
        existing.is_active = True
        existing.created_by = created_by
        code = existing
    else:
        code = ReferralCode(
            operator_id=operator_id,
            code=code_str,
            created_by=created_by,
        )
        db.add(code)

    await _log(
        db, "code_created",
        referrer_operator_id=operator_id,
        user_id=created_by,
        detail={"code": code_str},
    )
    await db.commit()
    await db.refresh(code)
    return code


async def set_code_active(
    db: AsyncSession, code_id: uuid.UUID, active: bool, user_id: uuid.UUID
) -> ReferralCode:
    """Habilita/deshabilita un código. NO afecta relaciones históricas."""
    code = await db.get(ReferralCode, code_id)
    if not code:
        raise ReferralError("Código no encontrado", 404)

    code.is_active = active
    await _log(
        db, "code_activated" if active else "code_deactivated",
        referrer_operator_id=code.operator_id,
        user_id=user_id,
        detail={"code": code.code},
    )
    await db.commit()
    await db.refresh(code)
    return code


async def validate_code(db: AsyncSession, code: str) -> ReferralCode:
    """Valida un código para registro público. Devuelve el ReferralCode.

    Raises ReferralError si: no existe, está deshabilitado o el referente
    está inactivo.
    """
    normalized = (code or "").strip().upper()
    if not normalized:
        raise ReferralError("Código de referido vacío", 400)

    rc = await db.scalar(select(ReferralCode).where(ReferralCode.code == normalized))
    if not rc:
        raise ReferralError("Código de referido inválido", 404)
    if not rc.is_active:
        raise ReferralError("Código de referido deshabilitado", 410)
    referrer = await db.get(Operator, rc.operator_id)
    if not referrer or not referrer.is_active:
        raise ReferralError("El referente ya no está activo", 410)
    return rc


async def register_referral(
    db: AsyncSession,
    *,
    code: str,
    referred_operator_id: uuid.UUID,
    user_id: uuid.UUID | None = None,
    commit: bool = True,
) -> Referral:
    """Crea la relación referido→referente al momento del registro.

    Se llama desde el registro público. Si el referido ya tiene referente,
    lanza error (relación única e inmutable).

    Con ``commit=False`` no hace commit: el llamador (p. ej. el registro
    público) confirma todo en una sola transacción atómica.
    """
    rc = await validate_code(db, code)

    existing = await db.scalar(
        select(Referral).where(Referral.referred_operator_id == referred_operator_id)
    )
    if existing:
        raise ReferralError("El operador ya tiene un referente registrado", 409)

    if rc.operator_id == referred_operator_id:
        raise ReferralError("No puedes referirte a ti mismo", 400)

    referral = Referral(
        referrer_operator_id=rc.operator_id,
        referred_operator_id=referred_operator_id,
        code_used=rc.code,
        registered_at=datetime.now(timezone.utc),
    )
    db.add(referral)
    await _log(
        db, "referral_registered",
        referrer_operator_id=rc.operator_id,
        referred_operator_id=referred_operator_id,
        user_id=user_id,
        detail={"code": rc.code},
    )
    if commit:
        await db.commit()
        await db.refresh(referral)
    return referral


async def get_referrer_metrics(db: AsyncSession, referrer_operator_id: uuid.UUID) -> dict:
    """Métricas DERIVADAS del referente (sin contadores +1/-1).

    - total_referrals:    personas referidas (COUNT referrals)
    - active_referrals:   referidos activos (operator.is_active)
    - assigned_referrals: referidos con >= 1 asignación activa
    - worked_referrals:   referidos con >= 1 asignación checked_in
    """
    referred_ids_q = select(Referral.referred_operator_id).where(
        Referral.referrer_operator_id == referrer_operator_id
    )

    total = (await db.scalar(
        select(func.count()).select_from(Referral).where(
            Referral.referrer_operator_id == referrer_operator_id
        )
    )) or 0

    active = (await db.scalar(
        select(func.count()).select_from(Referral)
        .join(Operator, Operator.id == Referral.referred_operator_id)
        .where(Referral.referrer_operator_id == referrer_operator_id,
               Operator.is_active == True)  # noqa: E712
    )) or 0

    assigned = (await db.scalar(
        select(func.count(func.distinct(EventAssignment.operator_id)))
        .select_from(EventAssignment)
        .where(
            EventAssignment.operator_id.in_(referred_ids_q),
            EventAssignment.is_active == True,  # noqa: E712
        )
    )) or 0

    worked = (await db.scalar(
        select(func.count(func.distinct(EventAssignment.operator_id)))
        .select_from(EventAssignment)
        .where(
            EventAssignment.operator_id.in_(referred_ids_q),
            EventAssignment.status == "checked_in",
        )
    )) or 0

    return {
        "total_referrals": total,
        "active_referrals": active,
        "assigned_referrals": assigned,
        "worked_referrals": worked,
    }


async def list_referrals_of(
    db: AsyncSession, referrer_operator_id: uuid.UUID
) -> list[Referral]:
    """Lista los referidos de un referente con datos del operador referido."""
    return list((await db.scalars(
        select(Referral)
        .where(Referral.referrer_operator_id == referrer_operator_id)
        .order_by(Referral.registered_at.desc())
    )).all())


async def list_audit_logs(
    db: AsyncSession, referrer_operator_id: uuid.UUID | None = None, limit: int = 50
) -> list[ReferralAuditLog]:
    """Historial de auditoría (global o por referente)."""
    q = select(ReferralAuditLog).order_by(ReferralAuditLog.created_at.desc()).limit(limit)
    if referrer_operator_id:
        q = q.where(ReferralAuditLog.referrer_operator_id == referrer_operator_id)
    return list((await db.scalars(q)).all())


async def get_referrer_operator_of(db: AsyncSession, operator_id: uuid.UUID) -> Operator | None:
    """Retorna el operador REFERENTE de un operador dado (None si no tiene).

    Lookup simple usado por la atribución de cupos (F11): cuando un operador
    con referente se asigna a un evento SIN coordinador explícito, el
    referente se estampa como programmed_by/admitted_by (regla R1: la
    elección explícita siempre gana). No registra auditoría (no es mutación).
    """
    ref = await db.scalar(
        select(Referral).where(Referral.referred_operator_id == operator_id)
    )
    if not ref:
        return None
    return await db.get(Operator, ref.referrer_operator_id)
