"""Seed the site content tables from the values currently hardcoded in home.html.

Run from the backend/ directory:

    python -m scripts.seed_site_content

Idempotent: uses upserts keyed by natural keys (section_key, title, image_url),
so it can be re-run safely after changes.
"""
from __future__ import annotations

import asyncio
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

# Ensure backend/ is importable when run as a script.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select  # noqa: E402

from app.database import AsyncSessionLocal  # noqa: E402
from app.models.content import (  # noqa: E402
    GalleryItem, NewsItem, ServiceItem, SiteSection, StageItem,
)


GALLERY_BASE = "/static/frontend/landing/gallery"


# --------------------------------------------------------------------------- #
# Sections                                                                     #
# --------------------------------------------------------------------------- #
SECTIONS = {
    "hero": {
        "eyebrow": "Logística y producción de eventos",
        "title": "Hacemos posible",
        "highlight": "grandes eventos.",
        "description": (
            "Planeamos, coordinamos y ejecutamos soluciones de logística, producción, "
            "seguridad, brigadas, protocolo y personal operativo para eventos de cualquier escala."
        ),
        "cta_primary": "Solicitar una cotización",
        "cta_secondary": "Conocer nuestros servicios",
        "trust": [
            {"value": "360°", "label": "Operación integral antes, durante y después del evento."},
            {"value": "24/7", "label": "Acompañamiento operativo para jornadas de alta exigencia."},
            {"value": "Bogotá", "label": "Experiencia en eventos públicos, privados y de gran formato."},
        ],
        "background_image": f"{GALLERY_BASE}/gallery_2.jpg",
    },
    "about": {
        "eyebrow": "Quiénes somos",
        "title": "Un equipo preparado para cuidar cada detalle.",
        "description": (
            "En A&C integramos talento humano, experiencia operativa y capacidad de respuesta "
            "para que cada evento se desarrolle con orden, seguridad y una ejecución impecable."
        ),
        "badge": "Operación humana, técnica y confiable",
        "main_image": f"{GALLERY_BASE}/gallery_7.jpg",
        "detail_image": f"{GALLERY_BASE}/gallery_3.jpg",
        "points": [
            {"title": "Planeación precisa",
             "description": "Diseñamos la operación de acuerdo con el tipo de evento, aforo, ubicación y necesidades del cliente."},
            {"title": "Personal capacitado",
             "description": "Conformamos equipos para logística, brigadas, protocolo, seguridad, control y apoyo operativo."},
            {"title": "Ejecución en campo",
             "description": "Acompañamos el evento en tiempo real y respondemos ante cambios, novedades y contingencias."},
        ],
    },
    "services_intro": {
        "eyebrow": "Nuestros servicios",
        "title": "Soluciones que se adaptan a cada evento.",
        "copy": (
            "Construimos equipos y operaciones a la medida para eventos corporativos, "
            "culturales, institucionales, comerciales y de entretenimiento."
        ),
    },
    "stages_intro": {
        "eyebrow": "Grandes escenarios",
        "title": "Hemos sido parte de eventos inolvidables.",
        "copy": (
            "Llevamos nuestra operación a escenarios de gran formato, acompañando "
            "a artistas, marcas y productoras que confían en A&C."
        ),
    },
    "gallery_intro": {
        "eyebrow": "Experiencia en campo",
        "title": "Personas, operación y presencia real.",
        "copy": (
            "Nuestro trabajo se ve en cada montaje, cada recorrido, cada control y cada equipo "
            "que hace posible el evento."
        ),
    },
    "news_intro": {
        "eyebrow": "Noticias y novedades",
        "title": "Lo que está pasando en A&C.",
    },
    "contact": {
        "eyebrow": "Hablemos de tu evento",
        "title": "Construyamos una operación a tu medida.",
        "copy": (
            "Cuéntanos qué necesitas, dónde será el evento y qué tipo de personal u operación "
            "requieres. Te contactaremos con una propuesta a la medida."
        ),
        "items": [
            {"label": "Ubicación", "value": "Bogotá, Colombia"},
            {"label": "Correo", "value": "contacto@ayc-eventos.com", "href": "mailto:contacto@ayc-eventos.com"},
        ],
        "note": "Al enviar este formulario aceptas nuestra política de tratamiento de datos personales.",
    },
    "footer": {
        "brand_title": "A&C Logística y Producción de Eventos",
        "columns": [
            {"title": "Navegación", "links": [
                {"label": "Inicio", "href": "#inicio"},
                {"label": "Nosotros", "href": "#nosotros"},
                {"label": "Servicios", "href": "#servicios"},
                {"label": "Noticias", "href": "#noticias"},
                {"label": "Contacto", "href": "#contacto"},
            ]},
            {"title": "Operación", "links": [
                {"label": "Colaboradores", "href": "/colaboradores"},
                {"label": "Política de datos", "href": "/politica-datos"},
            ]},
        ],
        "copyright": "© A&C Eventos. Todos los derechos reservados.",
    },
}


# --------------------------------------------------------------------------- #
# Services                                                                     #
# --------------------------------------------------------------------------- #
SERVICES = [
    {
        "title": "Logística operativa",
        "description": (
            "Coordinamos el flujo completo del evento: recepción, distribución, "
            "apoyo operativo y control de aforo para que todo se cumpla en tiempo y forma."
        ),
        "icon": "logistica",
        "image_url": f"{GALLERY_BASE}/gallery_1.jpg",
        "sort_order": 1,
    },
    {
        "title": "Brigadas y prevención",
        "description": (
            "Brigadistas capacitados en primeros auxilios, prevención y atención de "
            "emergencias para mantener la seguridad en cada punto del evento."
        ),
        "icon": "brigadas",
        "image_url": f"{GALLERY_BASE}/gallery_4.jpg",
        "sort_order": 2,
    },
    {
        "title": "Seguridad y control",
        "description": (
            "Personal de seguridad y control de acceso que garantiza el orden, la "
            "filtración adecuada y el cumplimiento de los protocolos del evento."
        ),
        "icon": "seguridad",
        "image_url": f"{GALLERY_BASE}/gallery_2.jpg",
        "sort_order": 3,
    },
    {
        "title": "Montaje y producción",
        "description": (
            "Equipos de montaje, producción técnica y logística de materiales para dejar "
            "todo listo antes, durante y después del evento."
        ),
        "icon": "montaje",
        "image_url": f"{GALLERY_BASE}/gallery_3.jpg",
        "sort_order": 4,
    },
    {
        "title": "Protocolo y atención",
        "description": (
            "Personal de protocolo, recepción y atención al cliente para brindar una "
            "experiencia impecable a tus invitados."
        ),
        "icon": "protocolo",
        "image_url": f"{GALLERY_BASE}/gallery_5.jpg",
        "sort_order": 5,
    },
    {
        "title": "Personal especializado",
        "description": (
            "Seleccionamos y asignamos personal con la experiencia y el perfil técnico "
            "que tu evento requiere, desde coordinadores hasta apoyo operativo."
        ),
        "icon": "personal",
        "image_url": f"{GALLERY_BASE}/gallery_6.jpg",
        "sort_order": 6,
    },
]


# --------------------------------------------------------------------------- #
# Stages (Grandes Escenarios)                                                  #
# --------------------------------------------------------------------------- #
STAGES = [
    {
        "label": "Artista internacional",
        "title": "J Balvin — Los Lobos Tour",
        "image_url": f"{GALLERY_BASE}/gallery_2.jpg",
        "sort_order": 1,
    },
    {
        "label": "Festival de música",
        "title": "Rock al Parque",
        "image_url": f"{GALLERY_BASE}/gallery_3.jpg",
        "sort_order": 2,
    },
    {
        "label": "Evento corporativo",
        "title": "Convención Andina",
        "image_url": f"{GALLERY_BASE}/gallery_5.jpg",
        "sort_order": 3,
    },
    {
        "label": "Marca global",
        "title": "Bavaria Live",
        "image_url": f"{GALLERY_BASE}/gallery_7.jpg",
        "sort_order": 4,
    },
    {
        "label": "Gran formato",
        "title": "Estéreo Picnic",
        "image_url": f"{GALLERY_BASE}/gallery_1.jpg",
        "sort_order": 5,
    },
    {
        "label": "Deporte y entretenimiento",
        "title": "Copa América Fan Zone",
        "image_url": f"{GALLERY_BASE}/gallery_4.jpg",
        "sort_order": 6,
    },
]


# --------------------------------------------------------------------------- #
# Gallery                                                                      #
# --------------------------------------------------------------------------- #
GALLERY = [
    {"title": "Brigadista de A&C en operación",
     "image_url": f"{GALLERY_BASE}/gallery_7.jpg", "caption": "Operación en campo", "sort_order": 1},
    {"title": "Equipo A&C frente a escenario",
     "image_url": f"{GALLERY_BASE}/gallery_2.jpg", "caption": "Producción", "sort_order": 2},
    {"title": "Personal logístico de A&C",
     "image_url": f"{GALLERY_BASE}/gallery_5.jpg", "caption": "Logística", "sort_order": 3},
    {"title": "Equipo A&C en montaje de escenario",
     "image_url": f"{GALLERY_BASE}/gallery_3.jpg", "caption": "Montaje", "sort_order": 4},
]


# --------------------------------------------------------------------------- #
# News                                                                         #
# --------------------------------------------------------------------------- #
NEWS = [
    {
        "title": "A&C refuerza su operación para la temporada de eventos",
        "category": "Actualidad",
        "summary": (
            "Ampliamos nuestra capacidad operativa y nuestro equipo humano para atender "
            "la creciente demanda de eventos corporativos y de gran formato en Bogotá."
        ),
        "status": "published",
        "image_url": f"{GALLERY_BASE}/gallery_3.jpg",
        "published_at": datetime.now(timezone.utc),
        "sort_order": 1,
        "featured": True,
    },
    {
        "title": "Capacitación continua de nuestros brigadistas",
        "category": "Equipo",
        "summary": (
            "Nuestro equipo de brigadistas completa ciclos permanentes de formación en "
            "primeros auxilios, prevención y atención de emergencias."
        ),
        "status": "published",
        "image_url": None,
        "published_at": datetime.now(timezone.utc),
        "sort_order": 2,
        "featured": False,
    },
    {
        "title": "Nuevos servicios de protocolo y atención",
        "category": "Eventos",
        "summary": (
            "Incorporamos perfiles especializados en protocolo, recepción y atención al "
            "cliente para elevar la experiencia en cada evento."
        ),
        "status": "published",
        "image_url": None,
        "published_at": datetime.now(timezone.utc),
        "sort_order": 3,
        "featured": False,
    },
]


# --------------------------------------------------------------------------- #
# Upsert helpers (async)                                                       #
# --------------------------------------------------------------------------- #
async def _upsert_section(db, key: str, payload: dict) -> None:
    existing = (
        await db.execute(select(SiteSection).where(SiteSection.section_key == key))
    ).scalar_one_or_none()
    content = json.dumps(payload, ensure_ascii=False)
    if existing:
        existing.content = content
    else:
        db.add(SiteSection(section_key=key, content=content))


async def _upsert_by_title(db, model, items: list[dict]) -> None:
    for data in items:
        existing = (
            await db.execute(select(model).where(model.title == data["title"]))
        ).scalar_one_or_none()
        if existing:
            for k, v in data.items():
                setattr(existing, k, v)
        else:
            # 'featured' is metadata not in the model
            clean = {k: v for k, v in data.items() if k != "featured"}
            db.add(model(**clean))


async def _upsert_stages(db) -> None:
    for data in STAGES:
        existing = (
            await db.execute(
                select(StageItem).where(StageItem.title == data["title"])
            )
        ).scalar_one_or_none()
        if existing:
            for k, v in data.items():
                setattr(existing, k, v)
        else:
            db.add(StageItem(**data))


async def _upsert_gallery(db) -> None:
    for data in GALLERY:
        existing = (
            await db.execute(
                select(GalleryItem).where(GalleryItem.image_url == data["image_url"])
            )
        ).scalar_one_or_none()
        if existing:
            for k, v in data.items():
                setattr(existing, k, v)
        else:
            db.add(GalleryItem(**data))


async def main() -> None:
    print(">> Seeding site content...")
    async with AsyncSessionLocal() as db:
        try:
            for key, payload in SECTIONS.items():
                await _upsert_section(db, key, payload)
                print(f"  [OK] section '{key}'")

            await _upsert_by_title(db, ServiceItem, SERVICES)
            print(f"  [OK] {len(SERVICES)} services")

            await _upsert_stages(db)
            print(f"  [OK] {len(STAGES)} stages")

            await _upsert_gallery(db)
            print(f"  [OK] {len(GALLERY)} gallery items")

            await _upsert_by_title(db, NewsItem, NEWS)
            print(f"  [OK] {len(NEWS)} news items")

            await db.commit()
            print("[DONE] Site content seeded successfully.")
        except Exception as exc:
            await db.rollback()
            print(f"[ERROR] Error seeding site content: {exc}")
            raise


if __name__ == "__main__":
    asyncio.run(main())