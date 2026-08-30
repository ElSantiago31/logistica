# -*- coding: utf-8 -*-
"""Tests SEO - sitemap, robots.txt, metadatos de la home y noindex de rutas privadas."""
import re

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.main import app

TITLE_PREFIX = "Producci\u00f3n de Eventos en Bogot\u00e1"


@pytest_asyncio.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


class TestSitemap:
    @pytest.mark.asyncio
    async def test_sitemap_ok(self, client):
        r = await client.get("/sitemap.xml")
        assert r.status_code == 200
        assert "xml" in r.headers.get("content-type", "")
        body = r.text
        assert "<loc>" in body
        assert re.search(r"<loc>[^<]*/</loc>", body), "La home debe estar en el sitemap"
        assert "<lastmod>" in body

    @pytest.mark.asyncio
    async def test_sitemap_no_duplicados(self, client):
        r = await client.get("/sitemap.xml")
        locs = re.findall(r"<loc>([^<]+)</loc>", r.text)
        assert locs, "Sitemap vacio"
        for loc in locs:
            assert locs.count(loc) == 1, "URL duplicada en sitemap: %s" % loc


class TestRobots:
    @pytest.mark.asyncio
    async def test_robots_txt(self, client):
        r = await client.get("/robots.txt")
        assert r.status_code == 200
        body = r.text
        assert "Sitemap:" in body
        assert "Disallow: /admin" in body
        assert "Disallow: /api" in body

    @pytest.mark.asyncio
    async def test_robots_content_type(self, client):
        r = await client.get("/robots.txt")
        assert "text/plain" in r.headers.get("content-type", "")


class TestHomeSEO:
    @pytest.mark.asyncio
    async def test_home_meta_tags(self, client):
        r = await client.get("/")
        assert r.status_code == 200
        html = r.text
        assert '<link rel="canonical"' in html
        assert 'property="og:title"' in html
        assert 'property="og:image"' in html
        assert 'name="twitter:card"' in html
        assert "application/ld+json" in html

    @pytest.mark.asyncio
    async def test_home_jsonld_types(self, client):
        r = await client.get("/")
        html = r.text
        for t in ("LocalBusiness", "WebSite", "FAQPage"):
            assert '"@type": "%s"' % t in html, "Falta JSON-LD %s" % t

    @pytest.mark.asyncio
    async def test_home_title_keyword(self, client):
        r = await client.get("/")
        assert TITLE_PREFIX in r.text

    @pytest.mark.asyncio
    async def test_home_faq_visible(self, client):
        r = await client.get("/")
        assert 'id="faq"' in r.text
        assert "faq-item" in r.text

    @pytest.mark.asyncio
    async def test_home_lazy_images(self, client):
        r = await client.get("/")
        assert 'loading="lazy"' in r.text

    @pytest.mark.asyncio
    async def test_home_nap(self, client):
        r = await client.get("/")
        assert "tel:+576016438375" in r.text
        assert "info@ayceventos.com.co" in r.text


class TestNoindexPrivado:
    """Rutas privadas deben enviar X-Robots-Tag: noindex (middleware de main.py)."""

    @pytest.mark.asyncio
    async def test_admin_noindex(self, client):
        r = await client.get("/admin/login")
        assert "noindex" in r.headers.get("x-robots-tag", "").lower()

    @pytest.mark.asyncio
    async def test_api_noindex(self, client):
        r = await client.get("/api/__endpoint_inexistente__")
        assert "noindex" in r.headers.get("x-robots-tag", "").lower()

    @pytest.mark.asyncio
    async def test_home_indexable(self, client):
        r = await client.get("/")
        assert "noindex" not in r.headers.get("x-robots-tag", "").lower()
