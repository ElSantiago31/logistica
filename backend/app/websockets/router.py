"""Router de WebSockets — canal en tiempo real para check-in/intendencia/payroll.

Endpoint: ``GET /ws/{event_id}?token=<jwt>&channel=<checkin|intendencia|payroll>``

- Valida el JWT del operador/staff al conectar (igual que get_current_user).
- Registra el socket en el ConnectionManager (sala event_id + channel).
- Mantiene el socket vivo con un heartbeat (servidor→cliente cada 25s).
- El cliente debe responder "pong" (o cualquier mensaje) para confirmar.
- Si el token es inválido/expirado, cierra con código 4401 antes de aceptar.
"""
import asyncio
import logging
import uuid

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query, status
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.database import AsyncSessionLocal
from app.models.users import User
from app.services.auth import decode_token, is_token_revoked
from app.websockets.manager import manager

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/ws", tags=["WebSockets"])

# Heartbeat: cada 25s el servidor manda "ping". Si el cliente no responde en
# ~60s, el socket se considera muerto y se cierra (lo reconoce uvicorn).
HEARTBEAT_INTERVAL_S = 25
HEARTBEAT_TIMEOUT_S = 60

VALID_CHANNELS = {"checkin", "payroll"}


async def _validate_ws_token(token: str) -> User | None:
    """Valida el JWT del WS (mismo estándar que get_current_user).

    Returns:
        User si es válido, None si no.
    """
    if not token:
        return None
    try:
        payload = decode_token(token)
    except Exception as exc:
        logger.warning("[ws] decode_token lanzó excepción: %s", exc)
        return None
    if payload is None:
        return None
    if payload.get("type") != "access":
        return None

    jti = payload.get("jti")
    if jti:
        # Abrimos una sesión breve solo para validar revocación
        async with AsyncSessionLocal() as db:
            if await is_token_revoked(db, jti):
                return None

    user_id = payload.get("sub")
    if not user_id:
        return None

    try:
        uid = uuid.UUID(user_id)
    except (ValueError, TypeError):
        return None

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(User)
            .options(selectinload(User.role))
            .where(User.id == uid, User.is_active == True)
        )
        return result.scalar_one_or_none()


async def _heartbeat_loop(websocket: WebSocket) -> None:
    """Envía 'ping' periódicamente y cierra si no hay 'pong' a tiempo."""
    last_pong = asyncio.get_event_loop().time()
    try:
        while True:
            await asyncio.sleep(HEARTBEAT_INTERVAL_S)
            now = asyncio.get_event_loop().time()
            if now - last_pong > HEARTBEAT_TIMEOUT_S:
                logger.info("[ws] heartbeat timeout, cerrando socket")
                try:
                    await websocket.close(code=status.WS_1011_INTERNAL_ERROR)
                except Exception:
                    pass
                return
            try:
                await websocket.send_text(json_dumps({"type": "ping"}))
            except Exception:
                return
    except asyncio.CancelledError:
        return


def json_dumps(obj):
    import json
    return json.dumps(obj)


@router.websocket("/{event_id}")
async def ws_event_channel(
    websocket: WebSocket,
    event_id: str,
    token: str = Query(default=""),
    channel: str = Query(default="checkin"),
):
    """Canal WebSocket en tiempo real para un evento.

    Query params:
        token:   JWT de acceso (access_token).
        channel: "checkin" | "payroll".
    """
    # 1) Validar canal
    if channel not in VALID_CHANNELS:
        await websocket.close(code=4400, reason="Canal inválido")
        return

    # 2) Validar event_id (UUID)
    try:
        evt_uuid = uuid.UUID(event_id)
    except (ValueError, TypeError):
        await websocket.close(code=4400, reason="event_id inválido")
        return

    # 3) Validar token ANTES de aceptar la conexión
    user = await _validate_ws_token(token)
    if user is None:
        # 4401 = convención propia (401 en WS)
        await websocket.close(code=4401, reason="Token inválido o expirado")
        return

    # Etiqueta para logs
    user_label = (
        f"{user.first_name} {user.last_name}".strip()
        or user.email
        or f"user_{user.id}"
    )

    # 4) Aceptar y registrar
    await manager.connect(websocket, str(evt_uuid), channel, user_label)

    # Confirmar al cliente que está conectado
    await websocket.send_text(
        json_dumps(
            {
                "type": "connected",
                "event_id": str(evt_uuid),
                "channel": channel,
                "message": "Conexión en tiempo real activa",
            }
        )
    )

    # 5) Iniciar heartbeat en background
    heartbeat_task = asyncio.create_task(_heartbeat_loop(websocket))

    try:
        # 6) Loop de recepción (el cliente manda "pong" u otros comandos)
        while True:
            msg = await websocket.receive_text()

            # Respuesta al ping del heartbeat
            if msg in ("pong", "ping", ""):
                continue

            # El cliente puede pedir "sync" para forzar un refresco completo
            # (los endpoints HTTP siguen siendo la fuente de verdad de datos).
            if msg == "sync":
                await websocket.send_text(
                    json_dumps(
                        {
                            "type": "sync_request",
                            "message": "Refresca tus datos desde la API HTTP",
                        }
                    )
                )
                continue

            # Cualquier otro mensaje se ignora (canal unidireccional servidor→cliente)
            logger.debug("[ws] mensaje no reconocido de %s: %s", user_label, msg[:80])

    except WebSocketDisconnect:
        logger.info("[ws] cliente desconectado: %s", user_label)
    except Exception as exc:
        logger.warning("[ws] error en loop de %s: %s", user_label, exc)
    finally:
        heartbeat_task.cancel()
        await manager.disconnect(websocket)


@router.get("/stats")
async def ws_stats():
    """Endpoint de monitoreo: cuántas conexiones activas hay (solo admin)."""
    # No depende de get_current_user para no complicar el wiring; se protege
    # externamente por nginx/Cloudflare si hace falta. Es solo info de estado.
    return {
        "total_connections": manager.get_connection_count(),
        "rooms": manager.get_rooms_summary(),
    }