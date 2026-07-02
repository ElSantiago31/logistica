"""ConnectionManager en memoria para WebSockets (single-process).

Diseñado para correr con **1 worker de uvicorn** (ver entrypoint.sh). Si en el
futuro se migrara a múltiples workers, habría que sustituir este manager por
Redis pub/sub.

Estructura de "salas" (rooms):
    _connections = {
        "<event_id>": {
            "<channel>": { websocket1, websocket2, ... },
        }
    }

Canales soportados:
    - "checkin"     → estado de check-in y cupos en vivo
    - "intendencia" → devoluciones de indumentaria
    - "payroll"     → firmas y pagos de nómina

Un cliente se suscribe a UN canal de UN evento. Cuando un endpoint HTTP
modifica datos, llama a ``manager.publish(event_id, channel, ...)`` y el
manager empuja el mensaje a todos los clientes conectados a esa sala.
"""
import asyncio
import json
import logging
import time
from collections import defaultdict
from typing import Dict, Set

from fastapi import WebSocket

logger = logging.getLogger(__name__)


class ConnectionManager:
    """Gestiona conexiones WebSocket agrupadas por evento y canal."""

    def __init__(self) -> None:
        # Estructura: {event_id: {channel: set(WebSocket)}}
        self._connections: Dict[str, Dict[str, Set[WebSocket]]] = defaultdict(
            lambda: defaultdict(set)
        )
        # Info de cada socket para stats y depuración:
        # {id(ws): {"event_id":..., "channel":..., "user":..., "connected_at":...}}
        self._meta: Dict[int, dict] = {}
        # Lock para evitar race conditions en operaciones de modificación
        self._lock = asyncio.Lock()

    async def connect(
        self,
        websocket: WebSocket,
        event_id: str,
        channel: str,
        user_label: str = "",
    ) -> None:
        """Acepta y registra una nueva conexión WebSocket."""
        await websocket.accept()
        async with self._lock:
            self._connections[event_id][channel].add(websocket)
            self._meta[id(websocket)] = {
                "event_id": event_id,
                "channel": channel,
                "user": user_label,
                "connected_at": time.time(),
            }
        logger.info(
            "[ws] connect event=%s channel=%s user=%s (total en sala: %d)",
            event_id,
            channel,
            user_label,
            len(self._connections[event_id][channel]),
        )

    async def disconnect(self, websocket: WebSocket) -> None:
        """Elimina una conexión de todas las salas en las que esté."""
        async with self._lock:
            meta = self._meta.pop(id(websocket), None)
            if not meta:
                return
            event_id = meta.get("event_id")
            channel = meta.get("channel")
            if event_id and channel:
                self._connections.get(event_id, {}).get(channel, set()).discard(
                    websocket
                )
                # Limpieza de sets vacíos para no acumular memoria
                if event_id in self._connections:
                    if channel in self._connections[event_id]:
                        if not self._connections[event_id][channel]:
                            del self._connections[event_id][channel]
                    if not self._connections[event_id]:
                        del self._connections[event_id]
            logger.info(
                "[ws] disconnect event=%s channel=%s user=%s",
                event_id,
                channel,
                meta.get("user"),
            )

    async def publish(
        self,
        event_id: str,
        channel: str,
        message_type: str,
        data: dict | None = None,
    ) -> int:
        """Envía un mensaje a todos los clientes de un canal+evento.

        Es "best effort": si un socket falla al enviar, se desconecta
        silenciosamente (el cliente reconectará).

        Returns:
            Número de clientes a los que se les envió el mensaje.
        """
        payload = json.dumps(
            {
                "type": message_type,
                "event_id": event_id,
                "channel": channel,
                "data": data or {},
                "server_time": time.time(),
            }
        )

        # Copiar el set para no mutar mientras iteramos
        sockets = list(self._connections.get(event_id, {}).get(channel, set()))
        if not sockets:
            return 0

        sent = 0
        dead = []
        for ws in sockets:
            try:
                await ws.send_text(payload)
                sent += 1
            except Exception as exc:
                logger.debug("[ws] envío fallido, marcando como muerto: %s", exc)
                dead.append(ws)

        # Limpiar sockets muertos fuera del lock para no bloquear
        for ws in dead:
            await self.disconnect(ws)

        return sent

    async def publish_broadcast(self, event_id: str, message_type: str, data: dict | None = None) -> int:
        """Envía un mensaje a TODOS los canales de un evento (checkin+intendencia+payroll).

        Útil cuando una acción afecta a varias vistas a la vez (ej. un check-in
        cambia el cupo en checkin.html y también el estado en intendencia.html).
        """
        total = 0
        for channel in list(self._connections.get(event_id, {}).keys()):
            total += await self.publish(event_id, channel, message_type, data)
        return total

    def get_connection_count(self, event_id: str | None = None) -> int:
        """Retorna el número de conexiones activas (de un evento o total)."""
        if event_id:
            return sum(
                len(s) for s in self._connections.get(event_id, {}).values()
            )
        return sum(
            len(s)
            for channels in self._connections.values()
            for s in channels.values()
        )

    def get_rooms_summary(self) -> dict:
        """Resumen de salas activas (para endpoint de monitoreo)."""
        summary = {}
        for event_id, channels in self._connections.items():
            summary[event_id] = {
                channel: len(sockets) for channel, sockets in channels.items()
            }
        return summary


# Singleton global (un solo proceso → una sola instancia)
manager = ConnectionManager()