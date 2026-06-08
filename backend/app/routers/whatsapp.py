"""WhatsApp router — Zenvia API webhook + send endpoints."""
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.config import settings
from app.dependencies.auth import get_current_user
from app.services import whatsapp as svc

router = APIRouter(prefix="/api/whatsapp", tags=["WhatsApp"])


# --- Zenvia Webhook ---

@router.post("/webhook")
async def webhook_receive(request: Request, db: AsyncSession = Depends(get_db)):
    """Receive incoming Zenvia webhook events (messages + status updates).

    Configure this URL in Zenvia dashboard as webhook.
    Optional: validate token via query param for security.
    """
    # Optional token validation
    token = request.query_params.get("token", "")
    if settings.ZENVIA_WEBHOOK_TOKEN and token != settings.ZENVIA_WEBHOOK_TOKEN:
        return Response(content="Unauthorized", status_code=401)

    payload = await request.json()
    result = await svc.process_webhook_payload(db, payload)
    return Response(content="OK", status_code=200)


# --- Send endpoints ---

@router.post("/events/{event_id}/invite")
async def send_invitations(
    event_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """Queue/send WhatsApp invitations for invited operators."""
    if user.user_type not in ("admin", "superadmin", "coordinator"):
        raise HTTPException(403, "Sin permisos")
    messages = await svc.queue_invitations(db, event_id)
    mode = "zenvia" if svc._is_configured() else "simulation"
    return {"queued": len(messages), "mode": mode, "message": f"{len(messages)} invitaciones ({mode})"}


@router.post("/events/{event_id}/remind")
async def send_reminder(
    event_id: uuid.UUID,
    message_type: str = Query("reminder_1d", regex="^(reminder_1d|reminder_5d)$"),
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """Queue/send WhatsApp reminders for confirmed operators."""
    if user.user_type not in ("admin", "superadmin", "coordinator"):
        raise HTTPException(403, "Sin permisos")
    messages = await svc.queue_reminder(db, event_id, message_type)
    mode = "zenvia" if svc._is_configured() else "simulation"
    return {"queued": len(messages), "mode": mode, "message": f"{len(messages)} recordatorios ({mode})"}


@router.post("/send-pending")
async def send_pending(
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """Send pending messages (real via Zenvia or simulated)."""
    if user.user_type not in ("admin", "superadmin"):
        raise HTTPException(403, "Sin permisos")
    if svc._is_configured():
        return await svc.send_pending_real(db)
    return await svc.simulate_send_pending(db)


@router.get("/queue")
async def get_queue(
    event_id: Optional[uuid.UUID] = None,
    status: Optional[str] = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """Get WhatsApp message queue."""
    if user.user_type not in ("admin", "superadmin", "coordinator"):
        raise HTTPException(403, "Sin permisos")
    items, total = await svc.get_queue(db, event_id, status, limit, offset)
    return {"items": items, "total": total}


@router.get("/config-status")
async def config_status(user=Depends(get_current_user)):
    """Check if Zenvia API is configured (no secrets exposed)."""
    if user.user_type not in ("admin", "superadmin"):
        raise HTTPException(403, "Sin permisos")
    return {
        "configured": svc._is_configured(),
        "provider": "zenvia",
        "mode": "zenvia" if svc._is_configured() else "simulation",
        "api_key_set": bool(settings.ZENVIA_API_KEY),
        "channel_id_set": bool(settings.ZENVIA_CHANNEL_ID),
        "webhook_token_set": bool(settings.ZENVIA_WEBHOOK_TOKEN),
    }


@router.patch("/assignments/{assignment_id}/status")
async def update_assignment_status(
    assignment_id: uuid.UUID,
    new_status: str = Query(..., regex="^(confirmed|rejected|standby|no_show)$"),
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """Update assignment status (e.g., operator confirms/rejects)."""
    assignment = await svc.update_assignment_status(db, assignment_id, new_status)
    if not assignment:
        raise HTTPException(404, "Asignacion no encontrada")
    return {"status": new_status, "message": f"Estado actualizado a {new_status}"}