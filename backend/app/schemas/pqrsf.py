"""Pydantic schemas for PQRSF (public form + admin management)."""
import uuid
from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, EmailStr, Field


# Tipos válidos para request_type
RequestType = Literal[
    "petition", "complaint", "claim", "suggestion", "congratulation"
]

# Estados válidos
PqrsfStatus = Literal["new", "in_progress", "resolved", "closed"]

# Prioridades válidas
PqrsfPriority = Literal["low", "medium", "high"]


# ---------------------------------------------------------------------------
# Public submission (form on home.html)
# ---------------------------------------------------------------------------
class PqrsfSubmissionCreate(BaseModel):
    """Formulario público de PQRSF (sin auth)."""
    request_type: RequestType
    subject: str = Field(..., min_length=5, max_length=200)
    full_name: str = Field(..., min_length=2, max_length=160)
    email: EmailStr
    phone: Optional[str] = Field(None, max_length=40)
    company: Optional[str] = Field(None, max_length=160)
    message: str = Field(..., min_length=10, max_length=5000)
    consent: bool = Field(
        True,
        description="Aceptación de tratamiento de datos (Habeas Data)",
    )


class PqrsfSubmissionResponse(BaseModel):
    """Respuesta completa de una PQRSF (para el panel admin)."""
    id: uuid.UUID
    tracking_code: str
    request_type: str
    subject: str
    full_name: str
    email: str
    phone: Optional[str] = None
    company: Optional[str] = None
    message: str
    status: str
    priority: str
    assigned_to: Optional[uuid.UUID] = None
    resolved_at: Optional[datetime] = None
    contacted_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class PqrsfSubmissionPublic(BaseModel):
    """Respuesta pública tras crear una PQRSF (datos mínimos + tracking code)."""
    id: uuid.UUID
    tracking_code: str
    request_type: str
    subject: str
    status: str
    created_at: datetime

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Public tracking (search by code)
# ---------------------------------------------------------------------------
class PqrsfTrackResponse(BaseModel):
    """Respuesta reducida para el endpoint público de seguimiento."""
    tracking_code: str
    request_type: str
    subject: str
    status: str
    created_at: datetime
    resolved_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Admin updates
# ---------------------------------------------------------------------------
class PqrsfSubmissionUpdateStatus(BaseModel):
    status: PqrsfStatus
    assigned_to: Optional[uuid.UUID] = None


class PqrsfSubmissionUpdatePriority(BaseModel):
    priority: PqrsfPriority


# ---------------------------------------------------------------------------
# Admin respond (email)
# ---------------------------------------------------------------------------
class PqrsfRespondRequest(BaseModel):
    """Payload para responder una PQRSF por email desde el panel."""
    subject: str = Field(..., min_length=5, max_length=200)
    body: str = Field(..., min_length=10, max_length=5000)


class PqrsfResponseItem(BaseModel):
    """Item del historial de respuestas de una PQRSF."""
    id: uuid.UUID
    subject: str
    body: str
    sent: bool
    error_message: Optional[str] = None
    responded_by: Optional[uuid.UUID] = None
    created_at: datetime

    model_config = {"from_attributes": True}