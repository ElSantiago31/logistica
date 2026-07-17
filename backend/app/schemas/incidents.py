"""Pydantic schemas for operator incidents and bans."""
import uuid
from datetime import datetime
from typing import Optional, Literal

from pydantic import BaseModel, Field


# --- Incidents ---

class IncidentCreateRequest(BaseModel):
    """Payload para crear una novedad desde el módulo de incidencias."""
    event_id: uuid.UUID
    operator_id: uuid.UUID
    incident_type: Literal[
        "doble_turno", "llegada_tarde", "salida_anticipada", "incumplimiento",
        "llamado_atencion", "observacion", "otro", "veto",
    ]
    description: str = Field(..., min_length=3, max_length=2000)


class IncidentResponse(BaseModel):
    id: uuid.UUID
    event_id: uuid.UUID
    operator_id: uuid.UUID
    recorded_by: Optional[uuid.UUID] = None
    incident_type: str
    description: str
    is_veto: bool
    created_at: datetime
    # Campos denormalizados para la UI
    event_name: Optional[str] = None
    operator_name: Optional[str] = None
    operator_document: Optional[str] = None
    recorder_name: Optional[str] = None

    model_config = {"from_attributes": True}


# --- Bans ---

class BanCreateRequest(BaseModel):
    """Payload para vetar a un operador."""
    operator_id: uuid.UUID
    reason: str = Field(..., min_length=3, max_length=1000)
    observations: Optional[str] = Field(None, max_length=2000)
    event_id: Optional[uuid.UUID] = Field(
        None, description="Evento donde se originó el veto (opcional, para novedad)",
    )


class BanReactivateRequest(BaseModel):
    """Payload para reactivar (quitar veto) a un operador."""
    unban_reason: Optional[str] = Field(None, max_length=1000)


class BanResponse(BaseModel):
    id: uuid.UUID
    operator_id: uuid.UUID
    banned_by: Optional[uuid.UUID] = None
    reason: str
    observations: Optional[str] = None
    is_active: bool
    unbanned_by: Optional[uuid.UUID] = None
    unbanned_at: Optional[datetime] = None
    unban_reason: Optional[str] = None
    created_at: datetime
    # Campos denormalizados para la UI
    operator_name: Optional[str] = None
    operator_document: Optional[str] = None
    banner_name: Optional[str] = None

    model_config = {"from_attributes": True}


class OperatorBanStatusResponse(BaseModel):
    """Estado de veto de un operador (para checks rápidos en login/landing)."""
    operator_id: uuid.UUID
    is_banned: bool
    active_ban: Optional[BanResponse] = None