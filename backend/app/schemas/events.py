"""Pydantic schemas for Events."""
import uuid
from datetime import datetime
from typing import Optional, List

from pydantic import BaseModel, Field, model_validator


# --- Staff Need ---
class StaffNeedCreate(BaseModel):
    role_id: uuid.UUID
    quantity_needed: int = Field(ge=1)
    rate_per_shift: Optional[float] = None
    education_level: Optional[str] = Field(None, description="Nivel educativo minimo requerido")


class StaffNeedResponse(BaseModel):
    id: uuid.UUID
    role_id: uuid.UUID
    role_name: Optional[str] = None
    quantity_needed: int
    quantity_confirmed: int
    rate_per_shift: Optional[float]
    education_level: Optional[str] = None

    model_config = {"from_attributes": True}


# --- Coordinator Quota ---
class CoordinatorQuotaCreate(BaseModel):
    """Asignación de cupo a un coordinador (operador) en un evento nuevo."""
    operator_id: uuid.UUID
    quota: int = Field(ge=0, description="Cupo informativo (no bloquea la asignación)")


class CoordinatorQuotaResponse(BaseModel):
    id: uuid.UUID
    event_id: uuid.UUID
    coordinator_operator_id: Optional[uuid.UUID] = None
    coordinator: str
    quota: int
    # Conteo calculado en runtime (no es columna)
    used: int = 0
    available: Optional[int] = None

    model_config = {"from_attributes": True}


# --- Event ---
class EventCreate(BaseModel):
    name: str = Field(min_length=3, max_length=300)
    description: Optional[str] = None
    location: str = Field(min_length=3, max_length=500)
    address: Optional[str] = None
    city: Optional[str] = None
    start_date: datetime
    end_date: datetime
    setup_date: Optional[datetime] = None
    client_name: Optional[str] = None
    client_phone: Optional[str] = None
    notes: Optional[str] = None
    staff_needs: List[StaffNeedCreate] = []
    coordinator_quotas: List[CoordinatorQuotaCreate] = []

    @model_validator(mode='after')
    def validate_dates(self):
        if self.end_date <= self.start_date:
            raise ValueError('La fecha de fin debe ser posterior a la fecha de inicio')
        return self


class EventUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=3, max_length=300)
    description: Optional[str] = None
    location: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    setup_date: Optional[datetime] = None
    client_name: Optional[str] = None
    client_phone: Optional[str] = None
    notes: Optional[str] = None
    status: Optional[str] = Field(None, pattern="^(draft|published|in_progress|completed|cancelled)$")
    staff_needs: Optional[List[StaffNeedCreate]] = None
    coordinator_quotas: Optional[List[CoordinatorQuotaCreate]] = None


class EventResponse(BaseModel):
    id: uuid.UUID
    name: str
    slug: Optional[str]
    description: Optional[str]
    location: str
    address: Optional[str]
    city: Optional[str]
    start_date: datetime
    end_date: datetime
    setup_date: Optional[datetime]
    status: str
    created_by: Optional[uuid.UUID]
    client_name: Optional[str]
    client_phone: Optional[str]
    notes: Optional[str]
    staff_needs: List[StaffNeedResponse] = []
    coordinator_quotas: List[CoordinatorQuotaResponse] = []
    total_staff_needed: int = 0
    total_confirmed: int = 0
    created_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class EventListResponse(BaseModel):
    items: List[EventResponse]
    total: int


# --- Assignment ---
class AssignmentResponse(BaseModel):
    id: uuid.UUID
    event_id: uuid.UUID
    operator_id: uuid.UUID
    operator_user_id: Optional[str] = None
    role_id: Optional[uuid.UUID]
    role_name: Optional[str] = None
    operator_name: Optional[str] = None
    operator_phone: Optional[str] = None
    status: str
    invited_at: Optional[datetime]
    confirmed_at: Optional[datetime]
    rate_applied: Optional[float]
    operator_first_name: Optional[str] = None
    operator_last_name: Optional[str] = None
    operator_document_number: Optional[str] = None
    shirt_number: Optional[str] = None
    jacket_number: Optional[str] = None
    cap_number: Optional[str] = None

    model_config = {"from_attributes": True}


class AssignOperatorsRequest(BaseModel):
    """Assign multiple operators to an event."""
    operator_ids: List[uuid.UUID]
    role_id: Optional[uuid.UUID] = None
    rate_applied: Optional[float] = None
    # Operador-coordinador que programa/admite a estos operadores (nuevo flujo).
    programmed_by_operator_id: Optional[uuid.UUID] = None


# --- Importación masiva desde Excel ---
class ImportRowResult(BaseModel):
    """Resultado de una fila del Excel de importación."""
    row: int                                      # número de fila (1-based, sin header)
    document_number: Optional[str] = None
    full_name: Optional[str] = None
    status: str                                   # created | existing | already_assigned | error
    message: str                                  # descripción legible
    operator_id: Optional[str] = None             # uuid si se procesó
    warnings: List[str] = []                      # ej: "EPS no encontrada, queda NULL"


class ImportSummary(BaseModel):
    """Resumen de la importación masiva de operadores."""
    total_rows: int
    created: int                                  # operadores nuevos creados
    existing: int                                 # operadores ya en BD, asignados ahora
    already_assigned: int                         # operadores ya asignados a este evento
    assigned: int                                 # = created + existing (asignaciones exitosas)
    errors: int
    duration_seconds: float
    rows: List[ImportRowResult] = []              # detalle fila por fila
