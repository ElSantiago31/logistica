"""Service layer for site content management.

Centraliza toda la lógica de negocio del contenido del sitio público:
- Secciones (hero/about/contact) como JSON key/value.
- Servicios, noticias y galería (CRUD + reordenado).
- Solicitudes de contacto (bandeja de entrada pública).
- Carga de imágenes para noticias/galería con cuota y cleanup.

Este módulo es consumido por:
  - app.routers.content   (API REST del panel web admin)
  - app.routers.pages      (SSR de la home con Jinja2)
"""
from __future__ import annotations

import json
import os
import uuid
from datetime import datetime
from typing import Any, Optional

from fastapi import HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.content import (
    ContactRequest,
    GalleryItem,
    NewsItem,
    ServiceItem,
    SiteSection,
    StageItem,
)

# Tipos MIME permitidos para imágenes de contenido (noticias/galería).
ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp"}
MAX_IMAGE_SIZE = 5 * 1024 * 1024  # 5 MB


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------
def _content_upload_dir() -> str:
    """Directorio físico donde se guardan las imágenes de contenido."""
    path = settings.CONTENT_IMAGES_DIR
    os.makedirs(path, exist_ok=True)
    return path


def _serialize_section_content(raw: str | None) -> dict[str, Any]:
    """Des-serializa el JSON de una sección de forma segura."""
    if not raw:
        return {}
    try:
        data = json.loads(raw)
        if isinstance(data, dict):
            return data
    except (json.JSONDecodeError, TypeError):
        pass
    return {}


def _public_image_url(filename: str) -> str:
    """URL pública servida por nginx/FastAPI para imágenes de contenido."""
    return f"/static/content/{filename}"


# ---------------------------------------------------------------------------
# Homepage aggregate (para SSR y para API pública)
# ---------------------------------------------------------------------------
async def get_homepage_content(db: AsyncSession) -> dict[str, Any]:
    """Devuelve TODO el contenido público necesario para la home.

    Estructura:
        {
          "sections": {"hero": {...}, "about": {...}, "contact": {...}},
          "services": [ServiceItem, ...],
          "news":     [NewsItem published, ...],
          "gallery":  [GalleryItem, ...],
        }
    """
    # Sections
    sec_result = await db.execute(select(SiteSection))
    sections = {
        s.section_key: _serialize_section_content(s.content)
        for s in sec_result.scalars().all()
    }

    # Services (ordenados)
    svc_result = await db.execute(
        select(ServiceItem)
        .where(ServiceItem.is_active == True)
        .order_by(ServiceItem.sort_order, ServiceItem.created_at)
    )
    services = [
        {
            "id": str(s.id),
            "title": s.title,
            "description": s.description,
            "icon": s.icon,
            "image_url": s.image_url,
            "sort_order": s.sort_order,
        }
        for s in svc_result.scalars().all()
    ]

    # News (solo published)
    news_result = await db.execute(
        select(NewsItem)
        .where(NewsItem.is_active == True, NewsItem.status == "published")
        .order_by(NewsItem.sort_order, NewsItem.published_at.desc().nullslast())
    )
    news = [
        {
            "id": str(n.id),
            "title": n.title,
            "category": n.category,
            "summary": n.summary,
            "image_url": n.image_url,
            "published_at": n.published_at.isoformat() if n.published_at else None,
        }
        for n in news_result.scalars().all()
    ]

    # Gallery
    gal_result = await db.execute(
        select(GalleryItem)
        .where(GalleryItem.is_active == True)
        .order_by(GalleryItem.sort_order, GalleryItem.created_at)
    )
    gallery = [
        {
            "id": str(g.id),
            "title": g.title,
            "image_url": g.image_url,
            "caption": g.caption,
        }
        for g in gal_result.scalars().all()
    ]

    # Stages (Grandes Escenarios)
    stage_result = await db.execute(
        select(StageItem)
        .where(StageItem.is_active == True)
        .order_by(StageItem.sort_order, StageItem.created_at)
    )
    stages = [
        {
            "id": str(s.id),
            "label": s.label,
            "title": s.title,
            "event_date": s.event_date,
            "image_url": s.image_url,
        }
        for s in stage_result.scalars().all()
    ]

    return {
        "sections": sections,
        "services": services,
        "stages": stages,
        "news": news,
        "gallery": gallery,
    }


# ---------------------------------------------------------------------------
# Sections
# ---------------------------------------------------------------------------
async def upsert_section(
    db: AsyncSession, section_key: str, content: dict[str, Any]
) -> SiteSection:
    """Crea o actualiza una sección por su key."""
    result = await db.execute(
        select(SiteSection).where(SiteSection.section_key == section_key)
    )
    section = result.scalar_one_or_none()
    serialized = json.dumps(content, ensure_ascii=False)
    if section:
        section.content = serialized
    else:
        section = SiteSection(section_key=section_key, content=serialized)
        db.add(section)
    await db.commit()
    await db.refresh(section)
    return section


async def list_sections(db: AsyncSession) -> list[SiteSection]:
    result = await db.execute(
        select(SiteSection).order_by(SiteSection.section_key)
    )
    return list(result.scalars().all())


# ---------------------------------------------------------------------------
# Services
# ---------------------------------------------------------------------------
async def list_services(db: AsyncSession) -> list[ServiceItem]:
    result = await db.execute(
        select(ServiceItem)
        .order_by(ServiceItem.sort_order, ServiceItem.created_at)
    )
    return list(result.scalars().all())


async def create_service(db: AsyncSession, **kwargs: Any) -> ServiceItem:
    item = ServiceItem(**kwargs)
    db.add(item)
    await db.commit()
    await db.refresh(item)
    return item


async def update_service(
    db: AsyncSession, item_id: uuid.UUID, **kwargs: Any
) -> Optional[ServiceItem]:
    item = await db.get(ServiceItem, item_id)
    if not item:
        return None
    for key, value in kwargs.items():
        if value is not None and hasattr(item, key):
            setattr(item, key, value)
    await db.commit()
    await db.refresh(item)
    return item


async def delete_service(db: AsyncSession, item_id: uuid.UUID) -> bool:
    item = await db.get(ServiceItem, item_id)
    if not item:
        return False
    await db.delete(item)
    await db.commit()
    return True


# ---------------------------------------------------------------------------
# News
# ---------------------------------------------------------------------------
async def list_news(
    db: AsyncSession, status_filter: Optional[str] = None
) -> list[NewsItem]:
    stmt = select(NewsItem).order_by(
        NewsItem.sort_order, NewsItem.created_at.desc()
    )
    if status_filter:
        stmt = stmt.where(NewsItem.status == status_filter)
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def create_news(db: AsyncSession, **kwargs: Any) -> NewsItem:
    if kwargs.get("status") == "published" and not kwargs.get("published_at"):
        kwargs["published_at"] = datetime.utcnow()
    item = NewsItem(**kwargs)
    db.add(item)
    await db.commit()
    await db.refresh(item)
    return item


async def update_news(
    db: AsyncSession, item_id: uuid.UUID, **kwargs: Any
) -> Optional[NewsItem]:
    item = await db.get(NewsItem, item_id)
    if not item:
        return None
    # Si pasa a published y no tenía fecha, asignarla
    if (
        kwargs.get("status") == "published"
        and not item.published_at
        and not kwargs.get("published_at")
    ):
        kwargs["published_at"] = datetime.utcnow()
    for key, value in kwargs.items():
        if value is not None and hasattr(item, key):
            setattr(item, key, value)
    await db.commit()
    await db.refresh(item)
    return item


async def delete_news(db: AsyncSession, item_id: uuid.UUID) -> bool:
    item = await db.get(NewsItem, item_id)
    if not item:
        return False
    await db.delete(item)
    await db.commit()
    return True


# ---------------------------------------------------------------------------
# Stages (Grandes Escenarios)
# ---------------------------------------------------------------------------
async def list_stages(db: AsyncSession) -> list[StageItem]:
    result = await db.execute(
        select(StageItem).order_by(StageItem.sort_order, StageItem.created_at)
    )
    return list(result.scalars().all())


async def create_stage(db: AsyncSession, **kwargs: Any) -> StageItem:
    item = StageItem(**kwargs)
    db.add(item)
    await db.commit()
    await db.refresh(item)
    return item


async def update_stage(
    db: AsyncSession, item_id: uuid.UUID, **kwargs: Any
) -> Optional[StageItem]:
    item = await db.get(StageItem, item_id)
    if not item:
        return None
    for key, value in kwargs.items():
        if hasattr(item, key):
            setattr(item, key, value)
    await db.commit()
    await db.refresh(item)
    return item


async def delete_stage(db: AsyncSession, item_id: uuid.UUID) -> bool:
    item = await db.get(StageItem, item_id)
    if not item:
        return False
    await db.delete(item)
    await db.commit()
    return True


# ---------------------------------------------------------------------------
# Gallery
# ---------------------------------------------------------------------------
async def list_gallery(db: AsyncSession) -> list[GalleryItem]:
    result = await db.execute(
        select(GalleryItem).order_by(
            GalleryItem.sort_order, GalleryItem.created_at
        )
    )
    return list(result.scalars().all())


async def create_gallery_item(db: AsyncSession, **kwargs: Any) -> GalleryItem:
    item = GalleryItem(**kwargs)
    db.add(item)
    await db.commit()
    await db.refresh(item)
    return item


async def update_gallery_item(
    db: AsyncSession, item_id: uuid.UUID, **kwargs: Any
) -> Optional[GalleryItem]:
    item = await db.get(GalleryItem, item_id)
    if not item:
        return None
    for key, value in kwargs.items():
        if value is not None and hasattr(item, key):
            setattr(item, key, value)
    await db.commit()
    await db.refresh(item)
    return item


async def delete_gallery_item(db: AsyncSession, item_id: uuid.UUID) -> bool:
    item = await db.get(GalleryItem, item_id)
    if not item:
        return False
    await db.delete(item)
    await db.commit()
    return True


# ---------------------------------------------------------------------------
# Contact requests
# ---------------------------------------------------------------------------
async def create_contact_request(
    db: AsyncSession, **kwargs: Any
) -> ContactRequest:
    item = ContactRequest(**kwargs)
    db.add(item)
    await db.commit()
    await db.refresh(item)
    return item


async def list_contact_requests(
    db: AsyncSession, status_filter: Optional[str] = None
) -> list[ContactRequest]:
    stmt = select(ContactRequest).order_by(ContactRequest.created_at.desc())
    if status_filter:
        stmt = stmt.where(ContactRequest.status == status_filter)
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def update_contact_status(
    db: AsyncSession, item_id: uuid.UUID, new_status: str
) -> Optional[ContactRequest]:
    item = await db.get(ContactRequest, item_id)
    if not item:
        return None
    item.status = new_status
    await db.commit()
    await db.refresh(item)
    return item


async def delete_contact_request(
    db: AsyncSession, item_id: uuid.UUID
) -> bool:
    item = await db.get(ContactRequest, item_id)
    if not item:
        return False
    await db.delete(item)
    await db.commit()
    return True


# ---------------------------------------------------------------------------
# Image upload + orphan cleanup
# ---------------------------------------------------------------------------
async def upload_content_image(db: AsyncSession, file: UploadFile) -> str:
    """Sube una imagen de contenido (noticia/galería) y retorna la URL pública.

    Aplica cuota global (MAX_CONTENT_IMAGES) y validación de tipo/tamaño.
    """
    # Validar tipo MIME
    if file.content_type not in ALLOWED_IMAGE_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Tipo de archivo no permitido. Solo JPEG, PNG o WEBP.",
        )

    # Validar tamaño leyendo el contenido en memoria
    data = await file.read()
    if len(data) > MAX_IMAGE_SIZE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="La imagen excede el tamaño máximo de 5MB.",
        )

    # Cuota: contar imágenes actuales (news + gallery no nulas)
    news_count = await db.execute(
        select(NewsItem).where(NewsItem.image_url.isnot(None))
    )
    gallery_count = await db.execute(
        select(GalleryItem).where(GalleryItem.image_url.isnot(None))
    )
    total = len(news_count.scalars().all()) + len(gallery_count.scalars().all())
    if total >= settings.CONTENT_MAX_IMAGES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cuota máxima de imágenes ({settings.CONTENT_MAX_IMAGES}) alcanzada. "
            "Elimina alguna antes de subir una nueva.",
        )

    # Guardar archivo
    ext = (file.filename or "image.jpg").split(".")[-1].lower()
    if ext not in {"jpg", "jpeg", "png", "webp"}:
        ext = "jpg"
    filename = f"{uuid.uuid4().hex}.{ext}"
    target_dir = _content_upload_dir()
    target_path = os.path.join(target_dir, filename)
    with open(target_path, "wb") as f:
        f.write(data)

    return _public_image_url(filename)


async def cleanup_orphan_images(db: AsyncSession) -> int:
    """Elimina del disco las imágenes de /static/content que ya no están en BD.

    Retorna el número de archivos eliminados. Llamado por un cron/tarea
    periódica o manualmente desde un endpoint admin.
    """
    # Recolectar URLs referenciadas
    news = await db.execute(select(NewsItem.image_url))
    gallery = await db.execute(select(GalleryItem.image_url))
    used: set[str] = {
        u
        for u in news.scalars().all()
        if u and "/static/content/" in u
    }
    used.update(
        u for u in gallery.scalars().all() if u and "/static/content/" in u
    )

    target_dir = _content_upload_dir()
    if not os.path.isdir(target_dir):
        return 0

    deleted = 0
    for fname in os.listdir(target_dir):
        url = f"/static/content/{fname}"
        if url not in used:
            try:
                os.remove(os.path.join(target_dir, fname))
                deleted += 1
            except OSError:
                continue
    return deleted