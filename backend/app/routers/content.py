"""Content router — API REST para gestión del contenido del sitio público.

Endpoints:
  PÚBLICOS (sin auth):
    - GET  /api/content/homepage          Agrega todo el contenido para SSR
    - POST /api/content/contact            Formulario público de contacto

  GESTIÓN (require_content_manager: superadmin, admin, web_admin):
    - GET    /api/content/sections         Lista secciones (hero/about/contact)
    - PUT    /api/content/sections/{key}   Crea/actualiza una sección
    - GET    /api/content/services         Lista servicios
    - POST   /api/content/services         Crea servicio
    - PUT    /api/content/services/{id}    Actualiza servicio
    - DELETE /api/content/services/{id}    Elimina servicio
    - GET    /api/content/news             Lista noticias (filtro status)
    - POST   /api/content/news             Crea noticia
    - PUT    /api/content/news/{id}        Actualiza noticia
    - DELETE /api/content/news/{id}        Elimina noticia
    - GET    /api/content/gallery          Lista galería
    - POST   /api/content/gallery          Crea item de galería
    - PUT    /api/content/gallery/{id}     Actualiza item
    - DELETE /api/content/gallery/{id}     Elimina item
    - POST   /api/content/upload           Sube imagen (noticia/galería)
    - POST   /api/content/cleanup          Limpia imágenes huérfanas
    - GET    /api/content/contacts         Lista solicitudes de contacto
    - PUT    /api/content/contacts/{id}    Cambia estado (new|read|archived)
"""
from __future__ import annotations

import uuid
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies.auth import require_content_manager
from app.models.content import (
    GalleryItem,
    NewsItem,
    ServiceItem,
    SiteSection,
)
from app.models.users import User
from app.schemas.content import (
    ContactRequestCreate,
    ContactRequestResponse,
    ContactRequestUpdate,
    GalleryItemCreate,
    GalleryItemResponse,
    GalleryItemUpdate,
    HomepageContent,
    NewsItemCreate,
    NewsItemResponse,
    NewsItemUpdate,
    SectionResponse,
    SectionUpsert,
    ServiceItemCreate,
    ServiceItemResponse,
    ServiceItemUpdate,
)
from app.services import content as content_service

router = APIRouter(prefix="/api/content", tags=["Site Content"])


# ---------------------------------------------------------------------------
# Public endpoints (no auth)
# ---------------------------------------------------------------------------
@router.get("/homepage", response_model=HomepageContent)
async def get_public_homepage(db: AsyncSession = Depends(get_db)):
    """Contenido público agregado para SSR / frontend de la home."""
    data = await content_service.get_homepage_content(db)
    return HomepageContent(**data)


@router.post("/contact", response_model=ContactRequestResponse, status_code=201)
async def submit_contact_form(
    payload: ContactRequestCreate,
    db: AsyncSession = Depends(get_db),
):
    """Formulario público de contacto — sin autenticación."""
    item = await content_service.create_contact_request(
        db,
        full_name=payload.full_name,
        email=payload.email,
        phone=payload.phone,
        company=payload.company,
        event_type=payload.event_type,
        message=payload.message,
    )
    return ContactRequestResponse.model_validate(item)


# ---------------------------------------------------------------------------
# Sections (management)
# ---------------------------------------------------------------------------
@router.get("/sections", response_model=list[SectionResponse])
async def list_sections(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_content_manager),
):
    items = await content_service.list_sections(db)
    out: list[SectionResponse] = []
    for s in items:
        out.append(
            SectionResponse(
                id=s.id,
                section_key=s.section_key,
                content=content_service._serialize_section_content(s.content),
                updated_at=s.updated_at,
            )
        )
    return out


@router.put("/sections/{section_key}", response_model=SectionResponse)
async def upsert_section(
    section_key: Literal["hero", "about", "contact"],
    payload: SectionUpsert,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_content_manager),
):
    """Crea o actualiza una sección por su key."""
    section = await content_service.upsert_section(db, section_key, payload.content)
    return SectionResponse(
        id=section.id,
        section_key=section.section_key,
        content=content_service._serialize_section_content(section.content),
        updated_at=section.updated_at,
    )


# ---------------------------------------------------------------------------
# Services (management)
# ---------------------------------------------------------------------------
@router.get("/services", response_model=list[ServiceItemResponse])
async def list_services(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_content_manager),
):
    items = await content_service.list_services(db)
    return [ServiceItemResponse.model_validate(s) for s in items]


@router.post("/services", response_model=ServiceItemResponse, status_code=201)
async def create_service(
    payload: ServiceItemCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_content_manager),
):
    item = await content_service.create_service(
        db,
        title=payload.title,
        description=payload.description,
        icon=payload.icon,
        image_url=payload.image_url,
        sort_order=payload.sort_order,
    )
    return ServiceItemResponse.model_validate(item)


@router.put("/services/{item_id}", response_model=ServiceItemResponse)
async def update_service(
    item_id: uuid.UUID,
    payload: ServiceItemUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_content_manager),
):
    data = payload.model_dump(exclude_unset=True)
    item = await content_service.update_service(db, item_id, **data)
    if not item:
        raise HTTPException(404, "Servicio no encontrado")
    return ServiceItemResponse.model_validate(item)


@router.delete("/services/{item_id}", status_code=204)
async def delete_service(
    item_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_content_manager),
):
    ok = await content_service.delete_service(db, item_id)
    if not ok:
        raise HTTPException(404, "Servicio no encontrado")


# ---------------------------------------------------------------------------
# News (management)
# ---------------------------------------------------------------------------
@router.get("/news", response_model=list[NewsItemResponse])
async def list_news(
    status: str | None = Query(None, description="published | draft"),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_content_manager),
):
    items = await content_service.list_news(db, status_filter=status)
    return [NewsItemResponse.model_validate(n) for n in items]


@router.post("/news", response_model=NewsItemResponse, status_code=201)
async def create_news(
    payload: NewsItemCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_content_manager),
):
    item = await content_service.create_news(
        db,
        title=payload.title,
        category=payload.category,
        summary=payload.summary,
        status=payload.status,
        image_url=payload.image_url,
        sort_order=payload.sort_order,
    )
    return NewsItemResponse.model_validate(item)


@router.put("/news/{item_id}", response_model=NewsItemResponse)
async def update_news(
    item_id: uuid.UUID,
    payload: NewsItemUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_content_manager),
):
    data = payload.model_dump(exclude_unset=True)
    item = await content_service.update_news(db, item_id, **data)
    if not item:
        raise HTTPException(404, "Noticia no encontrada")
    return NewsItemResponse.model_validate(item)


@router.delete("/news/{item_id}", status_code=204)
async def delete_news(
    item_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_content_manager),
):
    ok = await content_service.delete_news(db, item_id)
    if not ok:
        raise HTTPException(404, "Noticia no encontrada")


# ---------------------------------------------------------------------------
# Gallery (management)
# ---------------------------------------------------------------------------
@router.get("/gallery", response_model=list[GalleryItemResponse])
async def list_gallery(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_content_manager),
):
    items = await content_service.list_gallery(db)
    return [GalleryItemResponse.model_validate(g) for g in items]


@router.post("/gallery", response_model=GalleryItemResponse, status_code=201)
async def create_gallery_item(
    payload: GalleryItemCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_content_manager),
):
    item = await content_service.create_gallery_item(
        db,
        title=payload.title,
        image_url=payload.image_url,
        caption=payload.caption,
        sort_order=payload.sort_order,
    )
    return GalleryItemResponse.model_validate(item)


@router.put("/gallery/{item_id}", response_model=GalleryItemResponse)
async def update_gallery_item(
    item_id: uuid.UUID,
    payload: GalleryItemUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_content_manager),
):
    data = payload.model_dump(exclude_unset=True)
    item = await content_service.update_gallery_item(db, item_id, **data)
    if not item:
        raise HTTPException(404, "Imagen de galería no encontrada")
    return GalleryItemResponse.model_validate(item)


@router.delete("/gallery/{item_id}", status_code=204)
async def delete_gallery_item(
    item_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_content_manager),
):
    ok = await content_service.delete_gallery_item(db, item_id)
    if not ok:
        raise HTTPException(404, "Imagen de galería no encontrada")


# ---------------------------------------------------------------------------
# Image upload
# ---------------------------------------------------------------------------
@router.post("/upload")
async def upload_image(
    file: UploadFile,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_content_manager),
):
    """Sube una imagen para noticias o galería. Retorna la URL pública."""
    url = await content_service.upload_content_image(db, file)
    return {"url": url}


@router.post("/cleanup")
async def cleanup_orphans(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_content_manager),
):
    """Elimina imágenes huérfanas del disco (no referenciadas en BD)."""
    deleted = await content_service.cleanup_orphan_images(db)
    return {"deleted": deleted}


# ---------------------------------------------------------------------------
# Contact requests (bandeja de entrada)
# ---------------------------------------------------------------------------
@router.get("/contacts", response_model=list[ContactRequestResponse])
async def list_contacts(
    status: str | None = Query(None, description="new | read | archived"),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_content_manager),
):
    items = await content_service.list_contact_requests(db, status_filter=status)
    return [ContactRequestResponse.model_validate(c) for c in items]


@router.put("/contacts/{contact_id}", response_model=ContactRequestResponse)
async def update_contact_status(
    contact_id: uuid.UUID,
    payload: ContactRequestUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_content_manager),
):
    item = await content_service.update_contact_status(
        db, contact_id, payload.status
    )
    if not item:
        raise HTTPException(404, "Solicitud de contacto no encontrada")
    return ContactRequestResponse.model_validate(item)