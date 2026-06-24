"""Pydantic schemas for Operators."""
import uuid
from datetime import date
from typing import Optional, List

from pydantic import BaseModel, EmailStr, Field, model_validator

# Base schema for shared attributes
class OperatorBase(BaseModel):
    phone: Optional[str] = Field(None, max_length=20)
    city: Optional[str] = Field(None, max_length=100)
    address: Optional[str] = Field(None, max_length=300)
    locality: Optional[str] = Field(None, max_length=150)
    blood_type: Optional[str] = Field(None, max_length=5)
    emergency_contact_name: Optional[str] = Field(None, max_length=200)
    emergency_contact_phone: Optional[str] = Field(None, max_length=20)
    whatsapp: Optional[str] = Field(None, max_length=20)
    eps_id: Optional[uuid.UUID] = None
    arl_id: Optional[uuid.UUID] = None
    has_protocol_experience: Optional[bool] = None
    event_size_experience: Optional[str] = Field(None, max_length=50)
    education_level: Optional[str] = Field(None, max_length=50)
    shirt_size: Optional[str] = Field(None, max_length=10)
    jacket_size: Optional[str] = Field(None, max_length=10)
    gender: Optional[str] = Field(None, max_length=20)

# For updating by the operator or admin
class OperatorUpdateRequest(OperatorBase):
    first_name: Optional[str] = Field(None, min_length=2, max_length=100)
    last_name: Optional[str] = Field(None, min_length=2, max_length=100)
    birth_date: Optional[date] = None
    gender: Optional[str] = Field(None, max_length=20)

# For admin updating sensitive fields
class OperatorAdminUpdateRequest(OperatorUpdateRequest):
    document_number: Optional[str] = Field(None, min_length=5, max_length=20)
    document_type: Optional[str] = Field(None, max_length=10)
    email: Optional[EmailStr] = None
    is_verified: Optional[bool] = None
    is_approved: Optional[bool] = None
    background_check_status: Optional[str] = Field(None, max_length=20)
    role_id: Optional[uuid.UUID] = None
    notes: Optional[str] = None
    is_active: Optional[bool] = None
    education_level: Optional[str] = Field(None, max_length=50)
    experience_roles: Optional[List[str]] = None

# Detailed response
class OperatorResponse(BaseModel):
    id: uuid.UUID
    email: str
    first_name: str
    last_name: str
    phone: Optional[str]
    document_type: str
    document_number: Optional[str]
    user_type: str
    role_id: Optional[uuid.UUID]
    is_verified: bool
    is_approved: bool
    is_active: bool
    last_login: Optional[str]
    notes: Optional[str]

    # Operator fields
    eps_id: Optional[uuid.UUID]
    arl_id: Optional[uuid.UUID]
    eps_name: Optional[str] = None
    arl_name: Optional[str] = None
    photo_path: Optional[str]
    photo_thumbnail_path: Optional[str]
    birth_date: Optional[date]
    gender: Optional[str]
    address: Optional[str]
    city: Optional[str]
    blood_type: Optional[str]
    emergency_contact_name: Optional[str]
    emergency_contact_phone: Optional[str]
    locality: Optional[str]
    whatsapp: Optional[str]
    has_protocol_experience: Optional[bool]
    event_size_experience: Optional[str]
    education_level: Optional[str]
    shirt_size: Optional[str]
    jacket_size: Optional[str]
    background_check_status: str
    background_check_date: Optional[date]
    experience_roles: Optional[str] = None
    rating_avg: Optional[float]
    total_events: int

    @model_validator(mode='before')
    @classmethod
    def flatten_operator_profile(cls, data):
        """Flatten operator_profile nested object into top-level fields."""
        if hasattr(data, 'operator_profile'):
            # It's a User ORM object
            profile = data.operator_profile
            values = {
                'id': data.id,
                'email': data.email,
                'first_name': data.first_name,
                'last_name': data.last_name,
                'phone': data.phone,
                'document_type': data.document_type,
                'document_number': data.document_number,
                'user_type': data.user_type,
                'role_id': data.role_id,
                'is_verified': data.is_verified,
                'is_approved': data.is_approved,
                'is_active': data.is_active,
                'last_login': str(data.last_login) if data.last_login else None,
                'notes': getattr(profile, 'notes', None) if profile else None,
            }
            if profile:
                eps_name = profile.eps.name if profile.eps else None
                arl_name = profile.arl.name if profile.arl else None
                values.update({
                    'eps_id': profile.eps_id,
                    'arl_id': profile.arl_id,
                    'eps_name': eps_name,
                    'arl_name': arl_name,
                    'photo_path': profile.photo_path,
                    'photo_thumbnail_path': profile.photo_thumbnail_path,
                    'birth_date': profile.birth_date,
                    'gender': profile.gender,
                    'address': profile.address,
                    'city': profile.city,
                    'blood_type': profile.blood_type,
                    'emergency_contact_name': profile.emergency_contact_name,
                    'emergency_contact_phone': profile.emergency_contact_phone,
                    'locality': profile.locality,
                    'whatsapp': profile.whatsapp,
                    'has_protocol_experience': profile.has_protocol_experience,
                    'event_size_experience': profile.event_size_experience,
                    'education_level': profile.education_level,
                    'shirt_size': profile.shirt_size,
                    'jacket_size': profile.jacket_size,
                    'background_check_status': profile.background_check_status or 'pending',
                    'background_check_date': profile.background_check_date,
                    'experience_roles': profile.experience_roles,
                    'rating_avg': profile.rating_avg,
                    'total_events': profile.total_events or 0,
                })
            else:
                values.update({
                    'eps_id': None, 'arl_id': None, 'eps_name': None, 'arl_name': None, 'photo_path': None,
                    'photo_thumbnail_path': None, 'birth_date': None, 'gender': None,
                    'address': None, 'city': None, 'blood_type': None,
                    'emergency_contact_name': None, 'emergency_contact_phone': None,
                    'locality': None, 'whatsapp': None,
                    'has_protocol_experience': None, 'event_size_experience': None,
                    'education_level': None,
                    'shirt_size': None, 'jacket_size': None,
                    'background_check_status': 'pending',
                    'background_check_date': None, 'experience_roles': None,
                    'rating_avg': None, 'total_events': 0,
                })
            return values
        return data

    model_config = {"from_attributes": True}

class OperatorListResponse(BaseModel):
    items: List[OperatorResponse]
    total: int