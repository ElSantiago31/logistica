# -*- coding: utf-8 -*-
"""Rutas SEO publicas: robots.txt y sitemap.xml."""
from datetime import datetime, timezone

from fastapi import APIRouter
from fastapi.responses import PlainTextResponse, Response

from app.config import settings

router = APIRouter(tags=["seo"])

ROBOTS_TXT = f"""User-agent: *
Allow: /
Disallow: /admin
Disallow: /api/
Disallow: /coordinador
Disallow: /staff
Disallow: /colaboradores
Disallow: /test-ui
Disallow: /static/photos/
Disallow: /static/rut/

Sitemap: {settings.SITE_URL}/sitemap.xml
"""


@router.get("/robots.txt", response_class=PlainTextResponse, include_in_schema=False)
async def robots_txt() -> PlainTextResponse:
    """robots.txt del sitio (rastreo permitido en home, bloqueado en rutas privadas)."""
    return PlainTextResponse(content=ROBOTS_TXT, media_type="text/plain; charset=utf-8")


@router.get("/sitemap.xml", response_class=Response, include_in_schema=False)
async def sitemap_xml() -> Response:
    """sitemap.xml con las URLs publicas indexables (home, enrolamiento, politica de datos)."""
    base = settings.SITE_URL
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    urls = [
        (f"{base}/", "1.0", "weekly", today),
        (f"{base}/enrolamiento", "0.3", "monthly", today),
        (f"{base}/politica-tratamiento-datos", "0.1", "yearly", today),
    ]
    entries = "\n".join(
        f"  <url>\n"
        f"    <loc>{loc}</loc>\n"
        f"    <lastmod>{lastmod}</lastmod>\n"
        f"    <changefreq>{freq}</changefreq>\n"
        f"    <priority>{prio}</priority>\n"
        f"  </url>"
        for loc, prio, freq, lastmod in urls
    )
    xml = (
        "<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n"
        "<urlset xmlns=\"http://www.sitemaps.org/schemas/sitemap/0.9\">\n"
        f"{entries}\n"
        "</urlset>"
    )
    return Response(content=xml, media_type="application/xml; charset=utf-8")
