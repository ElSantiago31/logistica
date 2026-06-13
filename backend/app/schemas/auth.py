"""Pydantic schemas for authentication."""
import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, EmailStr, Field


# --- Login ---
class LoginRequest(BaseModel):
    document_number: str = Field(..., min_length=5, max_length=20, description="Número de documento")
    password: str = Field(..., min_length=6, max_length=100)


class LoginResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int
    user: "UserBrief"


class UserBrief(BaseModel):
    id: uuid.UUID
    email: str
    first_name: str
    last_name: str
    user_type: str
    role_name: Optional[str] = None

    model_config = {"from_attributes": True}


# --- Register ---
class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=8, max_length=100)
    confirm_password: str = Field(..., min_length=8, max_length=100)
    first_name: str = Field(..., min_length=2, max_length=100)
    last_name: str = Field(..., min_length=2, max_length=100)
    phone: str = Field(..., min_length=7, max_length=20)
    document_type: str = Field(default="CC", max_length=10)
    document_number: str = Field(..., min_length=5, max_length=20)


class RegisterResponse(BaseModel):
    id: uuid.UUID
    email: str
    message: str


# --- Token ---
class RefreshTokenRequest(BaseModel):
    refresh_token: str


class TokenPayload(BaseModel):
    sub: str  # user_id
    email: str
    type: str  # access | refresh
    role: Optional[str] = None
    jti: str  # unique token identifier
    exp: int
    iat: int


# --- Change Password ---
class ChangePasswordRequest(BaseModel):
    current_password: str = Field(..., min_length=6)
    new_password: str = Field(..., min_length=8, max_length=100)
    confirm_new_password: str = Field(..., min_length=8, max_length=100)


# --- Operator Registration (public landing) ---
class OperatorRegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=6, max_length=100)
    first_name: str = Field(..., min_length=2, max_length=100)
    last_name: str = Field(..., min_length=2, max_length=100)
    phone: str = Field(..., min_length=7, max_length=20)
    document_type: str = Field(default="CC", max_length=10)
    document_number: str = Field(..., min_length=5, max_length=20)
    eps_id: Optional[uuid.UUID] = None
    arl_id: Optional[uuid.UUID] = None
    birth_date: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None
    locality: Optional[str] = None
    blood_type: Optional[str] = None
    emergency_contact_name: Optional[str] = None
    emergency_contact_phone: Optional[str] = None
    whatsapp: Optional[str] = None
    has_protocol_experience: Optional[bool] = None
    event_size_experience: Optional[str] = None
    education_level: Optional[str] = None
    shirt_size: Optional[str] = None
    jacket_size: Optional[str] = None
    experience_roles: Optional[list[str]] = None  # list of role IDs
