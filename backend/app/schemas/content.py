"""Pydantic schemas for site content (web admin panel + public homepage)."""
import uuid
from datetime import datetime
from typing import Optional, Literal, Any

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# SiteSection (hero, about, contact)
# ---------------------------------------------------------------------------
class SectionUpsert(BaseModel):
    """Payload para crear/actualizar una sección (JSON libre)."""
    section_key: Literal["hero", "about", "contact", "services_intro", "stages_intro"] = Field(..., description="Clave de la sección")
    content: dict[str, Any] = Field(..., description="Contenido serializable (JSON)")


class SectionResponse(BaseModel):
    id: uuid.UUID
    section_key: str
    content: dict[str, Any]
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# ServiceItem
# ---------------------------------------------------------------------------
class ServiceItemCreate(BaseModel):
    title: str = Field(..., min_length=2, max_length=120)
    description: str = Field(..., min_length=5, max_length=2000)
    icon: Optional[str] = Field(None, max_length=50)
    image_url: Optional[str] = Field(None, max_length=255)
    sort_order: int = Field(0, ge=0)


class ServiceItemUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=2, max_length=120)
    description: Optional[str] = Field(None, min_length=5, max_length=2000)
    icon: Optional[str] = Field(None, max_length=50)
    image_url: Optional[str] = Field(None, max_length=255)
    sort_order: Optional[int] = Field(None, ge=0)


class ServiceItemResponse(BaseModel):
    id: uuid.UUID
    title: str
    description: str
    icon: Optional[str] = None
    image_url: Optional[str] = None
    sort_order: int

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# NewsItem
# ---------------------------------------------------------------------------
class NewsItemCreate(BaseModel):
    title: str = Field(..., min_length=2, max_length=160)
    category: str = Field(..., min_length=2, max_length=60)
    summary: str = Field(..., min_length=5, max_length=2000)
    status: Literal["published", "draft"] = "published"
    image_url: Optional[str] = Field(None, max_length=255)
    sort_order: int = Field(0, ge=0)


class NewsItemUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=2, max_length=160)
    category: Optional[str] = Field(None, min_length=2, max_length=60)
    summary: Optional[str] = Field(None, min_length=5, max_length=2000)
    status: Optional[Literal["published", "draft"]] = None
    image_url: Optional[str] = Field(None, max_length=255)
    sort_order: Optional[int] = Field(None, ge=0)


class NewsItemResponse(BaseModel):
    id: uuid.UUID
    title: str
    category: str
    summary: str
    status: str
    image_url: Optional[str] = None
    published_at: Optional[datetime] = None
    sort_order: int

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# StageItem (Grandes Escenarios)
# ---------------------------------------------------------------------------
class StageItemCreate(BaseModel):
    label: str = Field(..., min_length=2, max_length=80, description="Eyebrow (ej. 'Artista internacional')")
    title: str = Field(..., min_length=2, max_length=160, description="Título fuerte (ej. 'J Balvin')")
    image_url: str = Field(..., min_length=1, max_length=255)
    sort_order: int = Field(0, ge=0)


class StageItemUpdate(BaseModel):
    label: Optional[str] = Field(None, min_length=2, max_length=80)
    title: Optional[str] = Field(None, min_length=2, max_length=160)
    image_url: Optional[str] = Field(None, min_length=1, max_length=255)
    sort_order: Optional[int] = Field(None, ge=0)


class StageItemResponse(BaseModel):
    id: uuid.UUID
    label: str
    title: str
    image_url: str
    sort_order: int

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# GalleryItem
# ---------------------------------------------------------------------------
class GalleryItemCreate(BaseModel):
    title: str = Field(..., min_length=2, max_length=160)
    image_url: str = Field(..., min_length=1, max_length=255)
    caption: Optional[str] = Field(None, max_length=255)
    sort_order: int = Field(0, ge=0)


class GalleryItemUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=2, max_length=160)
    image_url: Optional[str] = Field(None, min_length=1, max_length=255)
    caption: Optional[str] = Field(None, max_length=255)
    sort_order: Optional[int] = Field(None, ge=0)


class GalleryItemResponse(BaseModel):
    id: uuid.UUID
    title: str
    image_url: str
    caption: Optional[str] = None
    sort_order: int

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# ContactRequest
# ---------------------------------------------------------------------------
class ContactRequestCreate(BaseModel):
    """Formulario público de contacto (sin auth)."""
    full_name: str = Field(..., min_length=2, max_length=160)
    email: str = Field(..., min_length=5, max_length=160)
    phone: Optional[str] = Field(None, max_length=40)
    company: Optional[str] = Field(None, max_length=160)
    event_type: Optional[str] = Field(None, max_length=80)
    message: str = Field(..., min_length=5, max_length=5000)


class ContactRequestUpdate(BaseModel):
    """Cambiar estado (leído/archivado) desde el panel web admin."""
    status: Literal["new", "read", "archived"]


class ContactRequestResponse(BaseModel):
    id: uuid.UUID
    full_name: str
    email: str
    phone: Optional[str] = None
    company: Optional[str] = None
    event_type: Optional[str] = None
    message: str
    status: str
    created_at: datetime

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Agregado para render SSR de la home
# ---------------------------------------------------------------------------
class HomepageContent(BaseModel):
    """Agrega todo el contenido público necesario para renderizar la home."""
    sections: dict[str, dict[str, Any]] = Field(default_factory=dict)
    services: list[ServiceItemResponse] = Field(default_factory=list)
    stages: list[StageItemResponse] = Field(default_factory=list)
    news: list[NewsItemResponse] = Field(default_factory=list)
    gallery: list[GalleryItemResponse] = Field(default_factory=list)
