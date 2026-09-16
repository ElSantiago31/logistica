"""Pydantic schemas for Events."""
import uuid
from datetime import datetime
from typing import Optional, List

from pydantic import BaseModel, Field, model_validator

from app.models.events import EVENT_STAGES, DEFAULT_STAGE

# Patrón de validación de etapa (una sola fuente de verdad: EVENT_STAGES).
_STAGE_PATTERN = f"^({'|'.join(EVENT_STAGES)})$"


class DeleteEventRequest(BaseModel):
    """Confirmación obligatoria para eliminar un evento (solo superadmin).

    El superadmin debe re-ingresar su contraseña de acceso para que la
    eliminación proceda (doble factor de confirmación).
    """
    password: str = Field(..., min_length=1)


# --- Staff Need ---
class StaffNeedCreate(BaseModel):
    role_id: uuid.UUID
    quantity_needed: int = Field(ge=1)
    rate_per_shift: Optional[float] = None
    education_level: Optional[str] = Field(None, description="Nivel educativo minimo requerido")
    stage: str = Field(DEFAULT_STAGE, pattern=_STAGE_PATTERN, description="Etapa: previa|avanzada|evento|desmontaje")


class StaffNeedResponse(BaseModel):
    id: uuid.UUID
    role_id: uuid.UUID
    role_name: Optional[str] = None
    quantity_needed: int
    quantity_confirmed: int
    rate_per_shift: Optional[float]
    education_level: Optional[str] = None
    stage: str = DEFAULT_STAGE

    model_config = {"from_attributes": True}


# --- Coordinator Quota ---
class CoordinatorQuotaCreate(BaseModel):
    """Asignación de cupo a un coordinador en un evento.

    Acepta dos modos mutuamente excluyentes:
      - operator_id (FK): coordinador real registrado en el sistema.
      - coordinator_name (texto libre): coordinador legacy importado de Excel,
        sin FK. Se conserva tal cual, NO se hace matching con ningún operador.
    """
    operator_id: Optional[uuid.UUID] = None
    coordinator_name: Optional[str] = Field(None, max_length=200, description="Nombre legacy (texto libre, sin FK)")
    quota: int = Field(ge=0, description="Cupo informativo (no bloquea la asignación)")
    stage: str = Field(DEFAULT_STAGE, pattern=_STAGE_PATTERN, description="Etapa: previa|avanzada|evento|desmontaje")

    @model_validator(mode='after')
    def validate_coordinator(self):
        if not self.operator_id and not self.coordinator_name:
            raise ValueError('Debe proveer operator_id o coordinator_name')
        return self


class CoordinatorQuotaResponse(BaseModel):
    id: uuid.UUID
    event_id: uuid.UUID
    coordinator_operator_id: Optional[uuid.UUID] = None
    coordinator: str
    quota: int
    stage: str = DEFAULT_STAGE
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
    # Resumen por etapa: {"previa": {"needed": n, "confirmed": m}, ...}
    by_stage: dict[str, dict] = {}
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
    stage: str = DEFAULT_STAGE
    # Computado en runtime: operador con ≥2 asignaciones (etapas) en el mismo evento.
    double_shift: bool = False
    operator_first_name: Optional[str] = None
    operator_last_name: Optional[str] = None
    operator_document_number: Optional[str] = None
    shirt_number: Optional[str] = None
    jacket_number: Optional[str] = None
    cap_number: Optional[str] = None
    # True: operador "solo evento" (Incorporación Rápida, usuario fantasma).
    is_event_only: Optional[bool] = None

    model_config = {"from_attributes": True}


class AssignOperatorsRequest(BaseModel):
    """Assign multiple operators to an event."""
    operator_ids: List[uuid.UUID]
    role_id: Optional[uuid.UUID] = None
    rate_applied: Optional[float] = None
    # Etapa a la que se asignan los operadores (default: evento).
    stage: str = Field(DEFAULT_STAGE, pattern=_STAGE_PATTERN, description="Etapa: previa|avanzada|evento|desmontaje")
    # Operador-coordinador que programa/admite a estos operadores (nuevo flujo).
    programmed_by_operator_id: Optional[uuid.UUID] = None
    # Nombre del coordinador (flujo legacy / fallback si no hay operator_id).
    # Se envía desde el frontend para garantizar que SIEMPRE quede estampado
    # el coordinador, incluso si la cuota es legacy (texto libre, sin FK).
    programmed_by_name: Optional[str] = Field(None, max_length=200)


# --- Importación masiva desde Excel ---
class ImportRowResult(BaseModel):
    """Resultado de una fila del Excel de importación."""
    row: int                                      # número de fila (1-based, sin header)
    document_number: Optional[str] = None
    full_name: Optional[str] = None
    status: str                                   # created | existing | already_assigned | updated | error
    message: str                                  # descripción legible
    operator_id: Optional[str] = None             # uuid si se procesó
    warnings: List[str] = []                      # ej: "EPS no encontrada, queda NULL"


class ImportSummary(BaseModel):
    """Resumen de la importación masiva de operadores."""
    total_rows: int
    created: int                                  # operadores nuevos creados
    existing: int                                 # operadores ya en BD, asignados ahora
    already_assigned: int                         # operadores ya asignados a este evento (sin cambios)
    updated: int = 0                              # re-importados con cambios aplicados (cargo/perfil/coordinador)
    assigned: int                                 # = created + existing (asignaciones exitosas)
    errors: int
    duration_seconds: float
    rows: List[ImportRowResult] = []              # detalle fila por fila


class ImportJobAccepted(BaseModel):
    """Respuesta 202 del POST de importación: el Excel se procesa en background."""
    job_id: str
    status: str                                   # queued
    status_url: str                               # GET para consultar progreso/resultado


class ImportJobStatus(BaseModel):
    """Estado de un job de importación en background."""
    job_id: str
    event_id: uuid.UUID
    status: str                                   # queued | running | completed | failed
    stage: Optional[str] = None                   # hashing | processing
    processed: int = 0
    total: int = 0
    error: Optional[str] = None
    summary: Optional[ImportSummary] = None       # presente al completar


# --- Incorporación Rápida (operador "solo evento") ---
class QuickAddRequest(BaseModel):
    """Payload del botón ⚡ Incorporación Rápida del detalle de evento.

    Crea (o reutiliza) un operador "fantasma" event_only y lo asigna al
    evento con status=confirmed, stage=evento. Si el documento ya existe
    como operador real, se asigna el existente (mode="existing").
    """
    primer_nombre: str = Field(min_length=1, max_length=100)
    segundo_nombre: Optional[str] = Field(None, max_length=100)
    primer_apellido: str = Field(min_length=1, max_length=100)
    segundo_apellido: Optional[str] = Field(None, max_length=100)
    document_type: str = Field(min_length=1, max_length=10, description="CC | CE | TI | PA")
    document_number: str = Field(min_length=3, max_length=20)


class QuickAddResponse(BaseModel):
    """Resultado de la Incorporación Rápida."""
    assignment_id: str
    operator_id: str
    user_id: str
    full_name: str
    document_number: str
    role_id: Optional[str] = None
    role_name: Optional[str] = None
    mode: str              # "ghost" (nuevo solo-evento) | "existing" (operador real existente)
    status: str            # "confirmed"
