"""PQRSF router — API REST para Peticiones, Quejas, Reclamos, Sugerencias, Felicitaciones.

Endpoints:
  PÚBLICOS (sin auth):
    - POST /api/pqrsf                       Crear PQRSF (rate limited 5/min)
    - GET  /api/pqrsf/track/{tracking_code} Estado público por código

  GESTIÓN (require_content_manager: superadmin, admin, web_admin):
    - GET    /api/pqrsf                     Lista con filtros (status/type/priority)
    - GET    /api/pqrsf/{item_id}           Detalle de una PQRSF
    - PUT    /api/pqrsf/{item_id}/status    Cambiar estado
    - PUT    /api/pqrsf/{item_id}/priority  Cambiar prioridad
    - POST   /api/pqrsf/{item_id}/respond   Responder por email (con historial)
    - GET    /api/pqrsf/{item_id}/responses Historial de respuestas
    - DELETE /api/pqrsf/{item_id}           Eliminar
"""

import uuid

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies.auth import require_content_manager
from app.dependencies.rate_limit import limiter
from app.models.users import User
from app.schemas.pqrsf import (
    PqrsfRespondRequest,
    PqrsfResponseItem,
    PqrsfSubmissionCreate,
    PqrsfSubmissionPublic,
    PqrsfSubmissionResponse,
    PqrsfSubmissionUpdatePriority,
    PqrsfSubmissionUpdateStatus,
    PqrsfTrackResponse,
)
from app.services import pqrsf as pqrsf_service
from app.services.pqrsf import get_smtp_status
from app.websockets.manager import manager

router = APIRouter(prefix="/api/pqrsf", tags=["PQRSF"])

# Sala global usada para notificaciones del panel admin (igual que content)
_GLOBAL_EVENT_ID = "_global_"
_CONTENT_CHANNEL = "content"


# ---------------------------------------------------------------------------
# Public endpoints (no auth)
# ---------------------------------------------------------------------------
@router.post("", response_model=PqrsfSubmissionPublic, status_code=201)
@limiter.limit("5/minute")
async def submit_pqrsf(
    request: Request,
    payload: PqrsfSubmissionCreate = Body(...),
    db: AsyncSession = Depends(get_db),
):
    """Formulario público de PQRSF — sin autenticación.

    Rate limited (5/min por IP) para prevenir spam/abuso del endpoint público.
    Genera un tracking code automáticamente que el ciudadano puede usar para
    consultar el estado de su solicitud.
    """
    if not payload.consent:
        raise HTTPException(
            400,
            "Debe aceptar la política de tratamiento de datos personales.",
        )

    item = await pqrsf_service.create_pqrsf_submission(
        db,
        request_type=payload.request_type,
        subject=payload.subject,
        full_name=payload.full_name,
        email=payload.email,
        phone=payload.phone,
        company=payload.company,
        message=payload.message,
    )

    # Notificar en tiempo real al panel admin (si hay alguien conectado)
    try:
        await manager.publish(
            _GLOBAL_EVENT_ID,
            _CONTENT_CHANNEL,
            "new_pqrsf",
            {
                "id": str(item.id),
                "tracking_code": item.tracking_code,
                "request_type": item.request_type,
                "subject": item.subject,
                "full_name": item.full_name,
                "created_at": item.created_at.isoformat() if item.created_at else None,
            },
        )
    except Exception:
        # Las notificaciones en tiempo real no deben romper el flujo público
        pass

    return PqrsfSubmissionPublic.model_validate(item)


@router.get("/track/{tracking_code}", response_model=PqrsfTrackResponse)
@limiter.limit("30/minute")
async def track_pqrsf(
    request: Request,
    tracking_code: str,
    db: AsyncSession = Depends(get_db),
):
    """Consulta pública del estado de una PQRSF por su código de seguimiento.

    Devuelve solo información mínima (sin datos personales del solicitante),
    suficiente para que el ciudadano sepa en qué estado está su solicitud.

    Rate limited (30/min por IP) para prevenir enumeración de códigos.
    """
    item = await pqrsf_service.get_pqrsf_by_tracking(db, tracking_code)
    if not item:
        raise HTTPException(404, "Código de seguimiento no encontrado.")
    return PqrsfTrackResponse.model_validate(item)


# ---------------------------------------------------------------------------
# Management endpoints (require_content_manager)
# ---------------------------------------------------------------------------
@router.get("", response_model=list[PqrsfSubmissionResponse])
async def list_pqrsf(
    status: str | None = Query(None, description="new|in_progress|resolved|closed"),
    type: str | None = Query(None, description="petition|complaint|claim|suggestion|congratulation"),
    priority: str | None = Query(None, description="low|medium|high"),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_content_manager),
):
    """Lista filtrada de PQRSF para el panel admin."""
    items = await pqrsf_service.list_pqrsf(
        db,
        status_filter=status,
        type_filter=type,
        priority_filter=priority,
    )
    return [PqrsfSubmissionResponse.model_validate(i) for i in items]


@router.get("/meta/smtp")
async def pqrsf_smtp_status(
    user: User = Depends(require_content_manager),
):
    """Estado de configuración SMTP para el panel admin de PQRSF.

    Permite mostrar al admin si los correos se están enviando realmente o
    si están en modo simulación (SMTP deshabilitado), para evitar la confusión
    de "respuesta enviada" cuando en realidad no salió ningún correo.
    """
    return get_smtp_status()


@router.get("/{item_id}", response_model=PqrsfSubmissionResponse)
async def get_pqrsf(
    item_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_content_manager),
):
    """Detalle de una PQRSF."""
    item = await pqrsf_service.get_pqrsf(db, item_id)
    if not item:
        raise HTTPException(404, "PQRSF no encontrada")
    return PqrsfSubmissionResponse.model_validate(item)


@router.put("/{item_id}/status", response_model=PqrsfSubmissionResponse)
async def update_pqrsf_status(
    item_id: uuid.UUID,
    payload: PqrsfSubmissionUpdateStatus,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_content_manager),
):
    """Cambia el estado de una PQRSF (new|in_progress|resolved|closed)."""
    item = await pqrsf_service.update_pqrsf_status(
        db, item_id, payload.status, payload.assigned_to
    )
    if not item:
        raise HTTPException(404, "PQRSF no encontrada")
    return PqrsfSubmissionResponse.model_validate(item)


@router.put("/{item_id}/priority", response_model=PqrsfSubmissionResponse)
async def update_pqrsf_priority(
    item_id: uuid.UUID,
    payload: PqrsfSubmissionUpdatePriority,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_content_manager),
):
    """Cambia la prioridad interna de una PQRSF (low|medium|high)."""
    item = await pqrsf_service.update_pqrsf_priority(
        db, item_id, payload.priority
    )
    if not item:
        raise HTTPException(404, "PQRSF no encontrada")
    return PqrsfSubmissionResponse.model_validate(item)


@router.post("/{item_id}/respond", response_model=PqrsfResponseItem, status_code=201)
@limiter.limit("20/minute")
async def respond_to_pqrsf(
    request: Request,
    item_id: uuid.UUID,
    payload: PqrsfRespondRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_content_manager),
):
    """Responde una PQRSF por email desde el panel admin.

    Guarda el registro en el historial (con asunto, cuerpo, si se envió OK
    o el error) y envía el email al ciudadano. La PQRSF pasa automáticamente
    a estado 'in_progress' si estaba en 'new'.
    """
    try:
        response = await pqrsf_service.respond_to_pqrsf(
            db,
            pqrsf_id=item_id,
            responded_by=user.id,
            subject=payload.subject,
            body=payload.body,
        )
    except ValueError as exc:
        raise HTTPException(404, str(exc))

    return PqrsfResponseItem.model_validate(response)


@router.get("/{item_id}/responses", response_model=list[PqrsfResponseItem])
async def list_pqrsf_responses(
    item_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_content_manager),
):
    """Historial de respuestas (emails) enviadas a una PQRSF."""
    items = await pqrsf_service.list_pqrsf_responses(db, item_id)
    return [PqrsfResponseItem.model_validate(r) for r in items]


@router.delete("/{item_id}", status_code=204)
async def delete_pqrsf(
    item_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_content_manager),
):
    """Elimina permanentemente una PQRSF (y sus respuestas por CASCADE)."""
    ok = await pqrsf_service.delete_pqrsf(db, item_id)
    if not ok:
        raise HTTPException(404, "PQRSF no encontrada")