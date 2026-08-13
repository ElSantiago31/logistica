"""Service layer para PQRSF.

Patrón: cada función recibe la sesión de BD y opera sobre los modelos.
Las funciones son async y devuelven instancias del modelo o listas.
"""
import logging
import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.pqrsf import PqrsfResponse, PqrsfSubmission
from app.services.email_sender import (
    render_pqrsf_response_email,
    send_email,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Tracking code generation
# ---------------------------------------------------------------------------
async def generate_tracking_code(db: AsyncSession) -> str:
    """Genera un código único secuencial por año: PQR-YYYY-NNNNN.

    El consecutivo se reinicia cada año natural (estándar colombiano para
    radicados). Se cuentan las PQRSF cuyo tracking_code empieza con el año
    actual y se suma 1.

    Ejemplos:
        PQR-2026-00001, PQR-2026-00002, ..., PQR-2026-00350
        PQR-2027-00001, PQR-2027-00002, ...
    """
    year = datetime.utcnow().year
    prefix = f"PQR-{year}-"

    # Contar cuántas PQRSF existen ya en este año
    result = await db.execute(
        select(func.count(PqrsfSubmission.id))
        .where(PqrsfSubmission.tracking_code.like(f"{prefix}%"))
    )
    count = result.scalar() or 0
    seq = count + 1

    return f"{prefix}{seq:05d}"  # 5 dígitos con ceros a la izquierda


# ---------------------------------------------------------------------------
# Public submission
# ---------------------------------------------------------------------------
async def create_pqrsf_submission(
    db: AsyncSession,
    *,
    request_type: str,
    subject: str,
    full_name: str,
    email: str,
    phone: Optional[str] = None,
    company: Optional[str] = None,
    message: str,
) -> PqrsfSubmission:
    """Crea una PQRSF desde el formulario público.

    Genera el tracking code automáticamente y la deja en estado 'new'.
    """
    tracking_code = await generate_tracking_code(db)

    item = PqrsfSubmission(
        tracking_code=tracking_code,
        request_type=request_type,
        subject=subject,
        full_name=full_name,
        email=email,
        phone=phone,
        company=company,
        message=message,
        status="new",
        priority="low",
    )
    db.add(item)
    await db.commit()
    await db.refresh(item)
    logger.info(
        "[PQRSF] Nueva solicitud %s tipo=%s de %s",
        tracking_code, request_type, email,
    )
    return item


async def get_pqrsf_by_tracking(
    db: AsyncSession, tracking_code: str
) -> Optional[PqrsfSubmission]:
    """Búsqueda pública por código exacto (endpoint de seguimiento ciudadano)."""
    result = await db.execute(
        select(PqrsfSubmission)
        .where(PqrsfSubmission.tracking_code == tracking_code)
    )
    return result.scalar_one_or_none()


# ---------------------------------------------------------------------------
# Admin CRUD
# ---------------------------------------------------------------------------
async def list_pqrsf(
    db: AsyncSession,
    *,
    status_filter: Optional[str] = None,
    type_filter: Optional[str] = None,
    priority_filter: Optional[str] = None,
    limit: int = 200,
) -> list[PqrsfSubmission]:
    """Lista filtrada de PQRSF, ordenadas por created_at desc."""
    stmt = select(PqrsfSubmission).order_by(PqrsfSubmission.created_at.desc())

    if status_filter:
        stmt = stmt.where(PqrsfSubmission.status == status_filter)
    if type_filter:
        stmt = stmt.where(PqrsfSubmission.request_type == type_filter)
    if priority_filter:
        stmt = stmt.where(PqrsfSubmission.priority == priority_filter)

    stmt = stmt.limit(limit)
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def get_pqrsf(
    db: AsyncSession, item_id: uuid.UUID
) -> Optional[PqrsfSubmission]:
    result = await db.execute(
        select(PqrsfSubmission).where(PqrsfSubmission.id == item_id)
    )
    return result.scalar_one_or_none()


async def update_pqrsf_status(
    db: AsyncSession,
    item_id: uuid.UUID,
    new_status: str,
    assigned_to: Optional[uuid.UUID] = None,
) -> Optional[PqrsfSubmission]:
    """Cambia el estado de una PQRSF.

    Si pasa a 'resolved' o 'closed', setea resolved_at automáticamente.
    """
    item = await get_pqrsf(db, item_id)
    if not item:
        return None

    item.status = new_status
    if assigned_to is not None:
        item.assigned_to = assigned_to

    if new_status in ("resolved", "closed") and not item.resolved_at:
        item.resolved_at = datetime.utcnow()

    await db.commit()
    await db.refresh(item)
    return item


async def update_pqrsf_priority(
    db: AsyncSession,
    item_id: uuid.UUID,
    priority: str,
) -> Optional[PqrsfSubmission]:
    item = await get_pqrsf(db, item_id)
    if not item:
        return None
    item.priority = priority
    await db.commit()
    await db.refresh(item)
    return item


async def delete_pqrsf(db: AsyncSession, item_id: uuid.UUID) -> bool:
    """Elimina permanentemente una PQRSF (y sus respuestas por CASCADE)."""
    item = await get_pqrsf(db, item_id)
    if not item:
        return False
    await db.delete(item)
    await db.commit()
    return True


# ---------------------------------------------------------------------------
# Respond (email)
# ---------------------------------------------------------------------------
async def list_pqrsf_responses(
    db: AsyncSession, pqrsf_id: uuid.UUID
) -> list[PqrsfResponse]:
    """Historial de respuestas de una PQRSF, ordenado por created_at desc."""
    result = await db.execute(
        select(PqrsfResponse)
        .where(PqrsfResponse.pqrsf_id == pqrsf_id)
        .order_by(PqrsfResponse.created_at.desc())
    )
    return list(result.scalars().all())


def get_smtp_status() -> dict:
    """Devuelve el estado de configuración SMTP para mostrarlo al admin.

    El panel usa esta info para avisar cuando los correos están en modo
    simulación (dev) o si falta configuración en producción.
    """
    return {
        "enabled": settings.SMTP_ENABLED,
        "simulated": not settings.SMTP_ENABLED,
        "configured": bool(settings.SMTP_HOST and settings.SMTP_USER),
        "host": settings.SMTP_HOST or "",
        "from_email": settings.SMTP_FROM,
        "reply_to": settings.PQRSF_REPLY_TO,
        "message": (
            "SMTP deshabilitado (SMTP_ENABLED=false). Las respuestas se "
            "guardan en el historial pero NO se envían al correo del "
            "solicitante. Configure SMTP en el archivo .env para enviar."
            if not settings.SMTP_ENABLED
            else (
                "SMTP habilitado pero falta SMTP_HOST/SMTP_USER."
                if not (settings.SMTP_HOST and settings.SMTP_USER)
                else "SMTP configurado correctamente."
            )
        ),
    }


async def respond_to_pqrsf(
    db: AsyncSession,
    *,
    pqrsf_id: uuid.UUID,
    responded_by: uuid.UUID,
    subject: str,
    body: str,
) -> PqrsfResponse:
    """Responde una PQRSF por email.

    Pasos:
        1. Crea el registro en site_pqrsf_responses con sent=False.
        2. Renderiza el HTML y envía el email.
        3. Actualiza sent=True (o error_message si falla).
        4. Actualiza contacted_at y estado de la PQRSF.

    El registro se guarda SIEMPRE (éxito, simulación o error de envío),
    para mantener auditoría completa. Si SMTP está deshabilitado (modo dev),
    `sent=False` y `error_message` indica que fue simulado. Si falla el SMTP
    en producción, el admin puede reintentar.
    """
    # 1. Crear registro de respuesta
    response = PqrsfResponse(
        pqrsf_id=pqrsf_id,
        responded_by=responded_by,
        subject=subject,
        body=body,
        sent=False,
    )
    db.add(response)
    await db.flush()  # obtener response.id sin cerrar la tx

    # 2. Cargar la PQRSF para datos del email
    pqrsf = await get_pqrsf(db, pqrsf_id)
    if not pqrsf:
        await db.rollback()
        raise ValueError(f"PQRSF {pqrsf_id} no encontrada")

    # 3. Renderizar y enviar email
    html_body = render_pqrsf_response_email(
        tracking_code=pqrsf.tracking_code,
        recipient_name=pqrsf.full_name,
        subject=subject,
        body=body,
    )

    smtp_simulated = not settings.SMTP_ENABLED

    try:
        await send_email(
            to_email=pqrsf.email,
            subject=subject,
            html_body=html_body,
        )
        if smtp_simulated:
            # Modo simulación (dev): send_email() solo loggea y retorna True.
            # NO se envió realmente, por lo que el registro queda sent=False.
            response.sent = False
            response.error_message = (
                "SMTP deshabilitado (SMTP_ENABLED=false): respuesta guardada "
                "en el historial pero NO enviada al solicitante. Habilite "
                "SMTP en el archivo .env para enviar correos reales."
            )
        else:
            response.sent = True
            response.error_message = None
    except Exception as exc:
        response.sent = False
        response.error_message = str(exc)[:500]
        logger.error(
            "[PQRSF] Error enviando respuesta a %s: %s",
            pqrsf.email, exc,
        )

    # 4. Actualizar la PQRSF: contacted_at + estado
    pqrsf.contacted_at = datetime.utcnow()
    if pqrsf.status == "new":
        pqrsf.status = "in_progress"

    await db.commit()
    await db.refresh(response)
    return response
