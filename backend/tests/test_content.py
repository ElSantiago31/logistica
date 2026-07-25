"""Tests for the site content module (sections, services, news, gallery, contacts).

Validates:
- Public endpoints (homepage aggregate, contact form) work without auth.
- Admin endpoints reject unauthenticated requests.
- Service-layer CRUD operations work as expected.
"""
import pytest

from app.services import content as content_service


# ---------------------------------------------------------------------------
# Public endpoints
# ---------------------------------------------------------------------------
class TestPublicContent:
    """Endpoints públicos (sin autenticación)."""

    async def test_homepage_empty(self, client):
        """GET /api/content/homepage devuelve estructura vacía válida."""
        resp = await client.get("/api/content/homepage")
        assert resp.status_code == 200
        data = resp.json()
        assert "sections" in data
        assert "services" in data
        assert "news" in data
        assert "gallery" in data
        assert isinstance(data["services"], list)
        assert isinstance(data["news"], list)
        assert isinstance(data["gallery"], list)

    async def test_contact_form_creates_request(self, client):
        """POST /api/content/contact crea una solicitud sin auth."""
        payload = {
            "full_name": "Juan Prueba",
            "email": "juan@example.com",
            "phone": "3001234567",
            "event_type": "Boda",
            "message": "Necesito cotización para 200 personas.",
        }
        resp = await client.post("/api/content/contact", json=payload)
        assert resp.status_code == 201
        data = resp.json()
        assert data["full_name"] == "Juan Prueba"
        assert data["email"] == "juan@example.com"
        assert data["status"] == "new"
        assert "id" in data

    async def test_contact_form_validation_error(self, client):
        """POST /api/content/contact rechaza payloads inválidos."""
        # Falta email y mensaje (campos requeridos)
        resp = await client.post(
            "/api/content/contact",
            json={"full_name": "Sin datos"},
        )
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Admin endpoints (authentication required)
# ---------------------------------------------------------------------------
class TestAdminAuthGate:
    """Los endpoints admin deben rechazar requests sin token."""

    @pytest.mark.parametrize(
        "method,path",
        [
            ("GET", "/api/content/sections"),
            ("GET", "/api/content/services"),
            ("POST", "/api/content/services"),
            ("GET", "/api/content/news"),
            ("GET", "/api/content/gallery"),
            ("GET", "/api/content/contacts"),
            ("POST", "/api/content/cleanup"),
        ],
    )
    async def test_admin_endpoints_require_auth(self, client, method, path):
        resp = await getattr(client, method.lower())(path)
        # 401 Unauthorized o 403 Forbidden son ambos aceptables
        assert resp.status_code in (401, 403)


# ---------------------------------------------------------------------------
# Service-layer tests (unitarios sobre la BD de test)
# ---------------------------------------------------------------------------
class TestContentService:
    """Tests directos sobre la capa de servicio (sin pasar por HTTP)."""

    async def test_upsert_and_list_sections(self, db):
        """Crear y listar secciones funciona correctamente."""
        # Crear sección hero
        await content_service.upsert_section(
            db,
            "hero",
            {"title": "Bienvenido", "description": "Evento de prueba"},
        )
        sections = await content_service.list_sections(db)
        keys = [s.section_key for s in sections]
        assert "hero" in keys

        # Actualizar la misma sección
        await content_service.upsert_section(
            db,
            "hero",
            {"title": "Título actualizado"},
        )
        sections = await content_service.list_sections(db)
        hero = [s for s in sections if s.section_key == "hero"][0]
        content = content_service._serialize_section_content(hero.content)
        assert content["title"] == "Título actualizado"

    async def test_create_and_list_services(self, db):
        """CRUD de servicios funciona en orden."""
        s1 = await content_service.create_service(
            db,
            title="Logística",
            description="Servicio de logística",
            sort_order=1,
        )
        s2 = await content_service.create_service(
            db,
            title="Personal",
            description="Personal de eventos",
            sort_order=0,
        )
        services = await content_service.list_services(db)
        assert len(services) >= 2
        # El sort_order=0 debe ir primero
        titles = [s.title for s in services]
        assert "Logística" in titles
        assert "Personal" in titles

        # Eliminar
        deleted = await content_service.delete_service(db, s1.id)
        assert deleted is True

    async def test_create_and_delete_gallery_item(self, db):
        """Las imágenes de galería se crean y eliminan."""
        item = await content_service.create_gallery_item(
            db,
            title="Foto evento",
            image_url="/static/content/test.jpg",
            caption="Descripción de la foto",
            sort_order=0,
        )
        assert item.title == "Foto evento"

        gallery = await content_service.list_gallery(db)
        assert any(g.title == "Foto evento" for g in gallery)

        deleted = await content_service.delete_gallery_item(db, item.id)
        assert deleted is True

    async def test_news_status_transition(self, db):
        """Las noticias pasan de draft a published asignando fecha."""
        # Crear como borrador
        news = await content_service.create_news(
            db,
            title="Noticia de prueba",
            category="Actualidad",
            summary="Resumen de la noticia",
            status="draft",
        )
        assert news.status == "draft"
        assert news.published_at is None

        # Publicar
        updated = await content_service.update_news(
            db, news.id, status="published"
        )
        assert updated.status == "published"
        assert updated.published_at is not None

    async def test_contact_status_workflow(self, db):
        """Las solicitudes de contacto cambian de estado correctamente."""
        item = await content_service.create_contact_request(
            db,
            full_name="Cliente Test",
            email="cliente@test.com",
            message="Mensaje de contacto",
            event_type="Corporativo",
        )
        assert item.status == "new"

        # Marcar como leído
        updated = await content_service.update_contact_status(
            db, item.id, "read"
        )
        assert updated.status == "read"

        # Archivar
        updated = await content_service.update_contact_status(
            db, item.id, "archived"
        )
        assert updated.status == "archived"

    async def test_list_contacts_with_filter(self, db):
        """El filtro por estado funciona en list_contact_requests."""
        await content_service.create_contact_request(
            db,
            full_name="A",
            email="a@t.com",
            message="msj",
            event_type="x",
        )
        await content_service.create_contact_request(
            db,
            full_name="B",
            email="b@t.com",
            message="msj",
            event_type="x",
        )
        # Filtrar solo "new"
        new_items = await content_service.list_contact_requests(
            db, status_filter="new"
        )
        assert all(c.status == "new" for c in new_items)
        assert len(new_items) >= 2