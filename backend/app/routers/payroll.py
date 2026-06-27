"""Payroll router — evaluations, payable list, sign, pay, invoice, sync."""
import re
import uuid
import time
import logging
import unicodedata
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

# Zona horaria Bogotá (UTC-5, Colombia no usa horario de verano)
BOGOTA_TZ = timezone(timedelta(hours=-5))


def _now_bogota() -> datetime:
    """Hora actual en zona horaria Bogotá (UTC-5).

    REEMPLAZA a datetime.utcnow() para evitar el bug de que PostgreSQL
    interpret el naive datetime como hora local.
    """
    return datetime.now(BOGOTA_TZ)


def _to_bogota_iso(dt) -> str | None:
    """Convierte un datetime a ISO 8601 con offset Bogotá (-05:00).

    Maneja 3 casos:
    1. None → None
    2. Naive datetime (sin tzinfo) → se asume UTC y se convierte a Bogotá
    3. Datetime con tzinfo → se convierte a Bogotá

    Nota: Los registros antiguos (con datetime.utcnow()) pueden tener el
    offset mal aplicado por PostgreSQL. Los nuevos usan _now_bogota().
    """
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(BOGOTA_TZ).isoformat()

from app.database import get_db  # noqa: E402
from app.dependencies.auth import get_current_user
from app.models.events import Event, EventAssignment, EventStaffNeed
from app.models.operators import Operator
from app.models.payroll import Evaluation, PayrollRecord
from app.models.roles import Role
from app.models.users import User

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/payroll", tags=["Payroll"])

_PERMITTED = ("admin", "superadmin", "coordinator")


def _to_uuid(val):
    """Convert string to UUID, return None if invalid/empty."""
    if val is None or val == "":
        return None
    if isinstance(val, uuid.UUID):
        return val
    try:
        return uuid.UUID(str(val))
    except (ValueError, AttributeError):
        return None


# ============================================================
# EVALUATIONS (sin cambios — sigue igual que antes)
# ============================================================

@router.post("/evaluations")
async def create_evaluation(
    payload: dict,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """Create post-event evaluation for an operator."""
    if user.user_type not in _PERMITTED:
        raise HTTPException(403, "Sin permisos")

    scores = [
        payload.get("punctuality_score", 3),
        payload.get("performance_score", 3),
        payload.get("appearance_score", 3),
        payload.get("attitude_score", 3),
    ]
    overall = round(sum(scores) / len(scores), 2)

    evaluation = Evaluation(
        event_id=payload["event_id"],
        operator_id=payload["operator_id"],
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


@router.get("/evaluations/{event_id}")
async def get_evaluations(
    event_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """Get all evaluations for an event."""
    if user.user_type not in _PERMITTED:
        raise HTTPException(403, "Sin permisos")

    result = await db.execute(
        select(Evaluation, Operator, User)
        .join(Operator, Operator.id == Evaluation.operator_id)
        .join(User, User.id == Operator.user_id)
        .where(Evaluation.event_id == event_id)
    )
    rows = result.all()

    return {
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
# PAYROLL — LISTA DE OPERADORES PAGABLES
# ============================================================

@router.get("/events/{event_id}/payable")
async def get_payable_operators(
    event_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """Lista operadores confirmed/checked_in con su cargo y monto a pagar.

    Estructura compatible con el buscador offline del frontend (mismo formato
    que /api/sync/events/{event_id}/offline-data).
    """
    if user.user_type not in _PERMITTED:
        raise HTTPException(403, "Sin permisos")

    event = await db.get(Event, event_id)
    if not event:
        raise HTTPException(404, "Evento no encontrado")

    # Asignaciones pagables: todos excepto rejected, no_show y sin_acreditacion
    # (sin_acreditacion = el establecimiento no dejó ingresar al operador a
    # trabajar, por lo tanto NO debe incluirse en nómina)
    result = await db.execute(
        select(EventAssignment, Operator, User, Role)
        .join(Operator, Operator.id == EventAssignment.operator_id)
        .join(User, User.id == Operator.user_id)
        .outerjoin(Role, Role.id == EventAssignment.role_id)
        .where(
            EventAssignment.event_id == event_id,
            ~EventAssignment.status.in_(["rejected", "no_show", "sin_acreditacion"]),
        )
    )
    rows = result.all()

    # [NÓMINA-V2] Mapa de coordinadores del evento (por área)
    area_to_coord, general_coord = await _build_coordinator_map(db, event_id)

    # Mapa staff_needs para tarifa por rol
    needs_result = await db.execute(
        select(EventStaffNeed).where(EventStaffNeed.event_id == event_id)
    )
    rate_by_role: dict[str, float] = {}
    for need in needs_result.scalars().all():
        rate_by_role[str(need.role_id)] = need.rate_per_shift or 0.0

    # Mapa de registros de pago existentes
    rec_result = await db.execute(
        select(PayrollRecord).where(PayrollRecord.event_id == event_id)
    )
    records_by_op: dict[str, PayrollRecord] = {
        str(r.operator_id): r for r in rec_result.scalars().all()
    }

    operators = []
    for assignment, operator, op_user, role in rows:
        op_id_str = str(operator.id)
        # Tarifa: rate_applied > rate_per_shift del rol > 0
        rate = assignment.rate_applied
        if rate is None and role:
            rate = rate_by_role.get(str(role.id), 0.0)
        if rate is None:
            rate = 0.0

        record = records_by_op.get(op_id_str)

        # [NÓMINA-V2] Determinar coordinador: quien lo programó (programmed_by)
        # tiene prioridad. Fallback: admitted_by → mapping por área → "Sin asignar".
        coord_name = assignment.programmed_by or assignment.admitted_by
        if not coord_name:
            coord_name = general_coord[0] if general_coord else "Sin asignar"
            if role and role.area and role.area in area_to_coord:
                coord_name = area_to_coord[role.area][0]

        operators.append({
            "assignment_id": str(assignment.id),
            "operator_id": op_id_str,
            "full_name": f"{op_user.first_name} {op_user.last_name}",
            "document_number": op_user.document_number or "",
            "role_name": role.name if role else "Operador",
            "status": assignment.status,
            "photo_url": operator.photo_thumbnail_path,
            "payment_amount": float(rate),
            "payroll_status": record.status if record else "pending",
            "payroll_record_id": str(record.id) if record else None,
            "invoice_number": record.invoice_number if record else None,
            "has_signature": bool(record and record.signature_data),
            "coordinator_name": coord_name,  # [NÓMINA-V2]
            # Uniformes asignados por intendencia
            "shirt_number": assignment.shirt_number or None,
            "jacket_number": assignment.jacket_number or None,
            "cap_number": assignment.cap_number or None,
            "uniform_returned_at": assignment.uniform_returned_at,  # NULL = pendiente
        })

    total = sum(o["payment_amount"] for o in operators)
    signed = sum(1 for o in operators if o["payroll_status"] in ("signed", "paid"))
    paid = sum(1 for o in operators if o["payroll_status"] == "paid")

    return {
        "event_id": str(event_id),
        "event_name": event.name,
        "operators": operators,
        "total": len(operators),
        "total_payroll": total,
        "total_signed": signed,
        "total_paid": paid,
    }


# ============================================================
# PAYROLL — FIRMAR
# ============================================================

@router.post("/assignments/{assignment_id}/sign")
async def sign_payroll(
    assignment_id: uuid.UUID,
    payload: dict,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """Guarda la firma del operador (base64 PNG) en su PayrollRecord."""
    if user.user_type not in _PERMITTED:
        raise HTTPException(403, "Sin permisos")

    signature_data = payload.get("signature_data")
    if not signature_data:
        raise HTTPException(400, "signature_data requerido (base64 PNG)")

    assignment = await db.get(EventAssignment, assignment_id)
    if not assignment:
        raise HTTPException(404, "Asignación no encontrada")

    # Buscar registro existente
    result = await db.execute(
        select(PayrollRecord).where(PayrollRecord.assignment_id == assignment_id)
    )
    record = result.scalar_one_or_none()

    if record and record.status == "paid":
        raise HTTPException(409, "El operador ya fue pagado, no se puede cambiar la firma")

    # Datos de tarifa (snapshot) — NO editable desde frontend, viene del evento
    role_name = None
    payment_amount = assignment.rate_applied or 0.0
    if assignment.role_id:
        role = await db.get(Role, assignment.role_id)
        if role:
            role_name = role.name
        if not payment_amount:
            need_result = await db.execute(
                select(EventStaffNeed).where(
                    EventStaffNeed.event_id == assignment.event_id,
                    EventStaffNeed.role_id == assignment.role_id,
                )
            )
            need = need_result.scalar_one_or_none()
            if need and need.rate_per_shift:
                payment_amount = need.rate_per_shift

    if record:
        record.signature_data = signature_data
        record.status = "signed"
        record.signed_at = _now_bogota()
        record.signed_by = user.id
        record.role_name_snapshot = role_name or record.role_name_snapshot
        if not record.payment_amount:
            record.payment_amount = payment_amount
    else:
        record = PayrollRecord(
            event_id=assignment.event_id,
            operator_id=assignment.operator_id,
            assignment_id=assignment.id,
            role_name_snapshot=role_name,
            payment_amount=payment_amount,
            signature_data=signature_data,
            status="signed",
            signed_at=_now_bogota(),
            signed_by=user.id,
            is_offline=payload.get("is_offline", False),
            device_id=payload.get("device_id"),
        )
        db.add(record)

    try:
        await db.commit()
    except Exception as exc:
        await db.rollback()
        logger.error("Error al firmar nómina: %s", exc)
        raise HTTPException(500, f"Error al guardar firma: {exc}")

    return {
        "status": "signed",
        "record_id": str(record.id),
        "signed_at": record.signed_at.isoformat() if record.signed_at else None,
    }


@router.patch("/assignments/{assignment_id}/uniform-return")
async def toggle_uniform_return(
    assignment_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """Marcar/desmarcar uniforme como devuelto por intendencia (toggle).

    Si uniform_returned_at es NULL → marca con fecha actual (devuelto).
    Si tiene fecha → NULL (pendiente de devolución).
    """
    if user.user_type not in _PERMITTED:
        raise HTTPException(403, "Sin permisos")

    assignment = await db.get(EventAssignment, assignment_id)
    if not assignment:
        raise HTTPException(404, "Asignación no encontrada")

    # Toggle: si tiene fecha, quítala; si no, ponla
    if assignment.uniform_returned_at:
        assignment.uniform_returned_at = None
    else:
        assignment.uniform_returned_at = _now_bogota()

    await db.commit()
    await db.refresh(assignment)

    return {
        "assignment_id": str(assignment.id),
        "uniform_returned_at": _to_bogota_iso(assignment.uniform_returned_at),
        "returned": assignment.uniform_returned_at is not None,
    }


# ============================================================
# PAYROLL — PAGAR + GENERAR FACTURA
# ============================================================

def _sanitize_event_name(name: str) -> str:
    """Sanitiza el nombre del evento para usarlo en el número de factura.

    - Espacios → guion bajo '_'
    - Acentos removidos (á→a, é→e, ñ→n, etc.)
    - Mayúsculas
    - Solo alfanuméricos, '_' y '-'
    """
    if not name:
        name = "EVENTO"
    # Quitar acentos
    name = unicodedata.normalize("NFKD", name)
    name = name.encode("ascii", "ignore").decode("ascii")
    # Espacios → _
    name = name.strip().replace(" ", "_")
    # Múltiples _ consecutivos → uno solo
    name = re.sub(r"_+", "_", name)
    # Solo alfanuméricos, _ y -
    name = re.sub(r"[^A-Z0-9_\-]", "", name.upper())
    # Quitar _ al inicio/final
    name = name.strip("_-")
    return name or "EVENTO"


async def _generate_invoice_number(db: AsyncSession, event_id: uuid.UUID) -> str:
    """Genera un número de factura secuencial por evento.

    Formato: FAC_{Evento_Sanitizado}_{0001}
    Ejemplo: FAC_BODA_CARLOS_Y_MARIA_0001
    """
    event = await db.get(Event, event_id)
    event_slug = _sanitize_event_name(event.name if event else "")
    prefix = f"FAC_{event_slug}_"

    # Contar facturas existentes con ese prefijo en el evento
    result = await db.execute(
        select(func.count(PayrollRecord.id)).where(
            PayrollRecord.event_id == event_id,
            PayrollRecord.invoice_number.like(f"{prefix}%"),
        )
    )
    count = result.scalar() or 0
    return f"{prefix}{count + 1:04d}"


@router.post("/records/{record_id}/pay")
async def pay_payroll(
    record_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """Marca el registro como pagado y genera el número de factura."""
    if user.user_type not in _PERMITTED:
        raise HTTPException(403, "Sin permisos")

    record = await db.get(PayrollRecord, record_id)
    if not record:
        raise HTTPException(404, "Registro no encontrado")

    if record.status == "paid":
        # Idempotente: ya pagado, retornar la factura existente
        return {
            "status": "paid",
            "record_id": str(record.id),
            "invoice_number": record.invoice_number,
            "paid_at": record.paid_at.isoformat() if record.paid_at else None,
        }

    if not record.signature_data:
        raise HTTPException(409, "El operador debe firmar antes de pagar")

    record.status = "paid"
    record.paid_at = _now_bogota()
    record.paid_by = user.id
    record.invoice_number = await _generate_invoice_number(db, record.event_id)

    try:
        await db.commit()
    except Exception as exc:
        await db.rollback()
        logger.error("Error al pagar nómina: %s", exc)
        raise HTTPException(500, f"Error al generar factura: {exc}")

    return {
        "status": "paid",
        "record_id": str(record.id),
        "invoice_number": record.invoice_number,
        "paid_at": record.paid_at.isoformat() if record.paid_at else None,
    }


# ============================================================
# PAYROLL — FACTURA / RECIBO
# ============================================================

@router.get("/invoices/{record_id}")
async def get_invoice(
    record_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """Devuelve todos los datos para renderizar la factura imprimible."""
    if user.user_type not in _PERMITTED:
        raise HTTPException(403, "Sin permisos")

    record = await db.get(PayrollRecord, record_id)
    if not record:
        raise HTTPException(404, "Registro no encontrado")

    event = await db.get(Event, record.event_id)
    operator = await db.get(Operator, record.operator_id)
    op_user = await db.get(User, operator.user_id) if operator else None

    return {
        "invoice_number": record.invoice_number,
        "paid_at": _to_bogota_iso(record.paid_at),
        "payment_amount": record.payment_amount,
        "role_name": record.role_name_snapshot,
        "signature_data": record.signature_data,
        "operator_name": f"{op_user.first_name} {op_user.last_name}" if op_user else "—",
        "operator_document": op_user.document_number if op_user else "",
        "operator_phone": op_user.phone if op_user else "",
        "event_name": event.name if event else "",
        "event_location": event.location if event else "",
        "event_date": _to_bogota_iso(event.start_date) if event and event.start_date else None,
        "company": "A&C Eventos",
    }


# ============================================================
# PAYROLL — SINCRONIZACIÓN OFFLINE
# ============================================================

@router.post("/sync")
async def sync_payroll_offline(
    payload: dict,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """Sincroniza firmas y pagos registrados offline.

    payload: { records: [{ assignment_id, operator_id, event_id, signature_data,
                            payment_amount, role_name, status, device_id }] }
    """
    if user.user_type not in _PERMITTED:
        raise HTTPException(403, "Sin permisos")

    records = payload.get("records", [])
    if not records:
        return {"synced": 0, "failed": 0, "total": 0}

    synced = 0
    failed = 0

    for idx, rec in enumerate(records):
        try:
            assignment_id = _to_uuid(rec.get("assignment_id"))
            if not assignment_id:
                failed += 1
                continue

            # ¿Ya existe registro para esta asignación?
            result = await db.execute(
                select(PayrollRecord).where(PayrollRecord.assignment_id == assignment_id)
            )
            existing = result.scalar_one_or_none()

            signature_data = rec.get("signature_data")
            status = rec.get("status", "signed")

            if existing:
                # Solo actualizar si está en estado anterior
                if existing.status == "pending":
                    existing.signature_data = signature_data or existing.signature_data
                    existing.status = status
                    existing.signed_at = _now_bogota()
                    existing.signed_by = user.id
                    existing.is_offline = True
                    if status == "paid" and not existing.invoice_number:
                        existing.paid_at = _now_bogota()
                        existing.paid_by = user.id
                        existing.invoice_number = await _generate_invoice_number(db, existing.event_id)
                elif existing.status == "signed" and status == "paid":
                    existing.status = "paid"
                    existing.paid_at = _now_bogota()
                    existing.paid_by = user.id
                    existing.invoice_number = await _generate_invoice_number(db, existing.event_id)
            else:
                # Crear nuevo registro
                new_status = status if status in ("signed", "paid") else "signed"
                invoice_number = None
                paid_at = None
                if new_status == "paid":
                    event_id = _to_uuid(rec.get("event_id"))
                    if event_id:
                        invoice_number = await _generate_invoice_number(db, event_id)
                    paid_at = _now_bogota()

                new_record = PayrollRecord(
                    event_id=_to_uuid(rec.get("event_id")),
                    operator_id=_to_uuid(rec.get("operator_id")),
                    assignment_id=assignment_id,
                    role_name_snapshot=rec.get("role_name"),
                    payment_amount=float(rec.get("payment_amount", 0)),
                    signature_data=signature_data,
                    status=new_status,
                    signed_at=_now_bogota(),
                    signed_by=user.id,
                    paid_at=paid_at,
                    paid_by=user.id if paid_at else None,
                    invoice_number=invoice_number,
                    is_offline=True,
                    device_id=rec.get("device_id"),
                )
                db.add(new_record)

            await db.commit()
            synced += 1
        except Exception as exc:
            await db.rollback()
            logger.error("Error sincronizando payroll record #%d: %s — %s", idx, exc, rec)
            failed += 1

    return {"synced": synced, "failed": failed, "total": len(records)}


# ============================================================
# [NÓMINA-V2 - inicio] POLLING TIEMPO REAL + PRESENCIA
# ============================================================
# Réplica del patrón de checkin_presence (sync.py) aplicado a nómina.
# Permite detectar en tiempo real si otro dispositivo ya firmó/pagó un
# operador, para evitar doble pago cuando hay varios usuarios simultáneos.


async def _build_coordinator_map(db: AsyncSession, event_id: uuid.UUID):
    """Construye el mapeo de coordinadores para un evento (por área).

    Copia del helper equivalente en sync.py para mantener sincronizado
    el mapeo de áreas a coordinadores en el endpoint /payable.

    Retorna:
        area_to_coord: dict {area: (coordinator_full_name, role_name)}
        general_coord: tuple (name, role_name) del Coordinador General (nivel 1) o None
    """
    result = await db.execute(
        select(EventAssignment, Operator, User, Role)
        .join(Operator, Operator.id == EventAssignment.operator_id)
        .join(User, User.id == Operator.user_id)
        .join(Role, Role.id == EventAssignment.role_id)
        .where(
            EventAssignment.event_id == event_id,
            Role.hierarchy_level <= 2,
        )
    )

    area_to_coord = {}
    general_coord = None
    for assignment, operator, op_user, role in result.all():
        full_name = f"{op_user.first_name} {op_user.last_name}"
        if role.hierarchy_level == 1:
            # Coordinador General — fallback global
            general_coord = (full_name, role.name)
        elif role.area:
            # Coordinador de área — mapea área -> coordinador
            if role.area not in area_to_coord:
                area_to_coord[role.area] = (full_name, role.name)

    return area_to_coord, general_coord


# {event_id_str: {device_id: (last_seen_epoch, user_name)}}
_payroll_presence: dict = {}
PAYROLL_PRESENCE_TTL_SECONDS = 15


def _register_payroll_presence(event_id: str, device_id: str, user_name: str):
    """Registra que un dispositivo está viendo la nómina del evento."""
    if not device_id:
        device_id = "anon"
    now = time.time()
    if event_id not in _payroll_presence:
        _payroll_presence[event_id] = {}
    _payroll_presence[event_id][device_id] = (now, user_name)


def _get_active_payroll_viewers(event_id: str):
    """Cuenta y lista dispositivos activos en la nómina del evento.

    Un dispositivo se considera activo si hizo polling en los últimos
    PAYROLL_PRESENCE_TTL_SECONDS segundos (default 15s).
    """
    now = time.time()
    presence = _payroll_presence.get(event_id, {})
    active = {
        did: (ts, name)
        for did, (ts, name) in presence.items()
        if now - ts <= PAYROLL_PRESENCE_TTL_SECONDS
    }
    _payroll_presence[event_id] = active
    viewers = [
        {"device_id": did, "user_name": name}
        for did, (_, name) in active.items()
    ]
    return len(active), viewers


@router.get("/events/{event_id}/status")
async def get_payroll_status(
    event_id: uuid.UUID,
    device_id: str = Query(default=None, description="ID del dispositivo"),
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """Endpoint ligero para polling en tiempo real de la nómina (anti-doble-pago).

    Retorna solo el estado de pago por asignación (payload pequeño), más
    presencia de dispositivos y pagos recientes.
    """
    if user.user_type not in _PERMITTED:
        raise HTTPException(403, "Sin permisos")

    # --- Registrar presencia ---
    viewer_name = (
        f"{user.first_name} {user.last_name}"
        if getattr(user, "first_name", None)
        else (user.email or "Usuario")
    )
    _register_payroll_presence(str(event_id), device_id or "anon", viewer_name)
    active_count, viewers = _get_active_payroll_viewers(str(event_id))

    # --- Estado de pago por asignación ---
    result = await db.execute(
        select(PayrollRecord).where(PayrollRecord.event_id == event_id)
    )
    records = result.scalars().all()

    # --- Pagos recientes (cualquier dispositivo) ---
    recent_payments = []
    try:
        recent_result = await db.execute(
            select(PayrollRecord, Operator, User)
            .join(Operator, Operator.id == PayrollRecord.operator_id)
            .join(User, User.id == Operator.user_id)
            .where(
                PayrollRecord.event_id == event_id,
                PayrollRecord.status == "paid",
            )
            .order_by(PayrollRecord.paid_at.desc())
            .limit(15)
        )
        for rec, op, op_user in recent_result.all():
            recent_payments.append({
                "operator_name": f"{op_user.first_name} {op_user.last_name}",
                "invoice_number": rec.invoice_number,
                "paid_at": _to_bogota_iso(rec.paid_at),
                "payment_amount": float(rec.payment_amount),
            })
    except Exception:
        pass

    return {
        "event_id": str(event_id),
        "updated_at": datetime.utcnow().isoformat(),
        "active_viewers": active_count,
        "viewers": viewers,
        "recent_payments": recent_payments,
        "records": [
            {
                "assignment_id": str(r.assignment_id) if r.assignment_id else None,
                "operator_id": str(r.operator_id),
                "record_id": str(r.id),
                "status": r.status,
                "has_signature": bool(r.signature_data),
                "invoice_number": r.invoice_number,
                "payment_amount": float(r.payment_amount),
            }
            for r in records
        ],
    }
# ============================================================
# [NÓMINA-V2 - fin]


# ============================================================
# PLANILLA DE PAGO POR COORDINADOR (Excel .xlsx)
# ============================================================
# Genera un Excel a partir de la plantilla
# ``Planilla_Logistica_Eventos.xlsx`` (con logo y formato). Se crea una hoja
# por cada coordinador, paginada a 20 operadores por hoja.
# Solo se incluyen operadores con status='checked_in'.

@router.get("/events/{event_id}/planilla-coordinador")
async def download_planilla_coordinador(
    event_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """Descarga la planilla de pago en Excel (.xlsx), una hoja por coordinador.

    Solo incluye operadores con ``status='checked_in'``. Si un coordinador
    tiene más de 20 operadores, se generan hojas adicionales paginadas.

    Requiere permisos admin/superadmin/coordinator.
    """
    if user.user_type not in _PERMITTED:
        raise HTTPException(403, "Sin permisos")

    event = await db.get(Event, event_id)
    if not event:
        raise HTTPException(404, "Evento no encontrado")

    # Operadores checked_in del evento, con datos para la planilla
    result = await db.execute(
        select(EventAssignment, Operator, User, Role)
        .join(Operator, Operator.id == EventAssignment.operator_id)
        .join(User, User.id == Operator.user_id)
        .outerjoin(Role, Role.id == EventAssignment.role_id)
        .where(
            EventAssignment.event_id == event_id,
            EventAssignment.status == "checked_in",
        )
    )
    rows = result.all()

    # Mapear áreas a coordinadores del evento
    area_to_coord, general_coord = await _build_coordinator_map(db, event_id)

    # Agrupar operadores por coordinador
    operators_by_coordinator: dict[str, list[dict]] = {}
    for assignment, operator, op_user, role in rows:
        # Determinar coordinador: quien lo programó (programmed_by) tiene
        # prioridad. Fallback: admitted_by → mapping por área → "Sin asignar".
        coord_name = assignment.programmed_by or assignment.admitted_by
        if not coord_name:
            coord_name = general_coord[0] if general_coord else "Sin asignar"
            if role and role.area and role.area in area_to_coord:
                coord_name = area_to_coord[role.area][0]

        operators_by_coordinator.setdefault(coord_name, []).append({
            "full_name": f"{op_user.first_name} {op_user.last_name}",
            "document_number": op_user.document_number or "",
            "address": operator.address or "",
            "phone": op_user.phone or "",
            "coordinator_name": coord_name,
            "jacket_number": assignment.jacket_number or "",
            "cap_number": assignment.cap_number or "",
        })

    # Generar el Excel
    from app.services.planilla_excel import generate_planilla_xlsx

    try:
        xlsx_bytes = generate_planilla_xlsx(
            event_name=event.name,
            event_date=event.start_date,
            event_location=event.location,
            operators_by_coordinator=operators_by_coordinator,
        )
    except FileNotFoundError as exc:
        logger.error("Plantilla no encontrada: %s", exc)
        raise HTTPException(500, "Plantilla de planilla no encontrada en el servidor")
    except Exception as exc:
        logger.error("Error generando planilla: %s", exc)
        raise HTTPException(500, f"Error al generar la planilla: {exc}")

    # Sanitizar nombre del evento para el filename
    safe_name = _sanitize_event_name(event.name)
    filename = f"Planilla_{safe_name}.xlsx"

    return StreamingResponse(
        iter([xlsx_bytes]),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
