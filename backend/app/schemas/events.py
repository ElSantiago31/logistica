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


class StaffNeedResponse(BaseModel):
    id: uuid.UUID
    role_id: uuid.UUID
    role_name: Optional[str] = None
    quantity_needed: int
    quantity_confirmed: int
    rate_per_shift: Optional[float]

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
    role_id: Optional[uuid.UUID]
    role_name: Optional[str] = None
    operator_name: Optional[str] = None
    operator_phone: Optional[str] = None
    status: str
    invited_at: Optional[datetime]
    confirmed_at: Optional[datetime]
    rate_applied: Optional[float]

    model_config = {"from_attributes": True}


class AssignOperatorsRequest(BaseModel):
    """Assign multiple operators to an event."""
    operator_ids: List[uuid.UUID]
    role_id: Optional[uuid.UUID] = None
    rate_applied: Optional[float] = None