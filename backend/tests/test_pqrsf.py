"""Tests para el módulo PQRSF.

Cubre:
- Creación pública de PQRSF (POST /api/pqrsf).
- Consulta de estado por tracking_code (GET /api/pqrsf/track/{code}).
- Listado admin (GET /api/pqrsf).
- Actualización de estado y prioridad (PUT).
- Eliminación (DELETE /api/pqrsf/{id}).
"""
from __future__ import annotations

import uuid
from datetime import datetime
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.dependencies.auth import require_content_manager
from app.database import get_db
from app.main import app as real_app
from app.models.pqrsf import PqrsfSubmission
from app.schemas.pqrsf import (
    PqrsfSubmissionCreate,
    PqrsfSubmissionPublic,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
@pytest_asyncio.fixture
async def client():
    transport = ASGITransport(app=real_app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture
def sample_payload():
    return {
        "request_type": "petition",
        "subject": "Solicitud de información de servicios",
        "message": "Me gustaría conocer la disponibilidad para un evento en diciembre.",
        "full_name": "Juan Pérez",
        "email": "juan@example.com",
        "phone": "3001234567",
        "company": "Empresa Demo",
        "consent": True,
    }


@pytest.fixture
def admin_user():
    from types import SimpleNamespace
    return SimpleNamespace(
        id=uuid.uuid4(),
        email="admin@example.com",
        full_name="Admin Test",
        user_type="web_admin",
        is_active=True,
    )


@pytest.fixture(autouse=True)
def override_auth_and_db(admin_user):
    """Override de get_db y require_content_manager en todos los tests."""
    async def fake_db():
        from unittest.mock import AsyncMock
        yield AsyncMock()

    async def fake_auth():
        return admin_user

    real_app.dependency_overrides[get_db] = fake_db
    real_app.dependency_overrides[require_content_manager] = fake_auth
    yield
    real_app.dependency_overrides.clear()


def make_submission(**overrides) -> PqrsfSubmission:
    defaults = dict(
        id=uuid.uuid4(),
        tracking_code="PQR-2026-00001-A7K2",
        request_type="petition",
        subject="Asunto de prueba",
        message="Mensaje de prueba",
        full_name="Usuario Prueba",
        email="test@example.com",
        phone="3000000000",
        company=None,
        status="new",
        priority="medium",
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    defaults.update(overrides)
    return PqrsfSubmission(**defaults)


# ---------------------------------------------------------------------------
# Tests del modelo
# ---------------------------------------------------------------------------
def test_pqrsf_submission_creation():
    s = make_submission(tracking_code="PQR-2026-00002-Q9M3")
    assert s.tracking_code == "PQR-2026-00002-Q9M3"
    assert s.status == "new"
    assert s.priority == "medium"


# ---------------------------------------------------------------------------
# Tests del schema
# ---------------------------------------------------------------------------
def test_schema_submission_create_consent_defaults_true(sample_payload):
    """Si consent se omite, el schema aplica el default True."""
    data = {k: v for k, v in sample_payload.items() if k != "consent"}
    obj = PqrsfSubmissionCreate(**data)
    assert obj.consent is True


def test_schema_submission_create_valid(sample_payload):
    obj = PqrsfSubmissionCreate(**sample_payload)
    assert obj.request_type == "petition"
    assert obj.consent is True


def test_schema_submission_public_has_tracking_code():
    obj = PqrsfSubmissionPublic(
        id=uuid.uuid4(),
        tracking_code="PQR-2026-00003-BX4R",
        request_type="complaint",
        subject="Test",
        status="new",
        created_at=datetime.utcnow(),
    )
    assert obj.tracking_code == "PQR-2026-00003-BX4R"


# ---------------------------------------------------------------------------
# Tests del router (con servicios mockeados)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
@patch("app.services.pqrsf.create_pqrsf_submission", new_callable=AsyncMock)
@patch("app.routers.pqrsf.manager.publish", new_callable=AsyncMock)
async def test_create_pqrsf_public_success(mock_publish, mock_create, client, sample_payload):
    """POST /api/pqrsf debe crear una PQRSF y retornar 201 con tracking_code."""
    submission = make_submission()
    mock_create.return_value = submission

    resp = await client.post("/api/pqrsf", json=sample_payload)
    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert "tracking_code" in data
    assert data["tracking_code"] == submission.tracking_code


@pytest.mark.asyncio
@patch("app.services.pqrsf.create_pqrsf_submission", new_callable=AsyncMock)
@patch("app.routers.pqrsf.manager.publish", new_callable=AsyncMock)
async def test_create_pqrsf_requires_consent(mock_publish, mock_create, client, sample_payload):
    """POST /api/pqrsf sin consent debe retornar 400."""
    payload = {**sample_payload, "consent": False}
    resp = await client.post("/api/pqrsf", json=payload)
    assert resp.status_code == 400


@pytest.mark.asyncio
@patch("app.services.pqrsf.get_pqrsf_by_tracking", new_callable=AsyncMock)
async def test_track_pqrsf_success(mock_get, client):
    """GET /api/pqrsf/track/{code} debe retornar el estado de la PQRSF."""
    submission = make_submission(tracking_code="PQR-2026-00001-A7K2")
    mock_get.return_value = submission

    resp = await client.get("/api/pqrsf/track/PQR-2026-00001-A7K2")
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["tracking_code"] == "PQR-2026-00001-A7K2"
    assert data["status"] == "new"


@pytest.mark.asyncio
@patch("app.services.pqrsf.get_pqrsf_by_tracking", new_callable=AsyncMock)
async def test_track_pqrsf_not_found(mock_get, client):
    """GET /api/pqrsf/track/{code} con código inexistente debe retornar 404."""
    mock_get.return_value = None

    resp = await client.get("/api/pqrsf/track/NO-EXISTE")
    assert resp.status_code == 404


@pytest.mark.asyncio
@patch("app.services.pqrsf.list_pqrsf", new_callable=AsyncMock)
async def test_list_pqrsf_admin(mock_list, client):
    """GET /api/pqrsf debe retornar la lista de PQRSF."""
    s1 = make_submission(tracking_code="PQR-2026-00001-A7K2")
    s2 = make_submission(tracking_code="PQR-2026-00002-Q9M3", status="in_progress")
    mock_list.return_value = [s1, s2]

    resp = await client.get("/api/pqrsf")
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert len(data) == 2


@pytest.mark.asyncio
@patch("app.services.pqrsf.update_pqrsf_status", new_callable=AsyncMock)
async def test_update_pqrsf_status(mock_update, client):
    """PUT /api/pqrsf/{id}/status debe actualizar el estado."""
    item_id = uuid.uuid4()
    updated = make_submission(id=item_id, status="resolved")
    mock_update.return_value = updated

    resp = await client.put(f"/api/pqrsf/{item_id}/status", json={"status": "resolved"})
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "resolved"


@pytest.mark.asyncio
@patch("app.services.pqrsf.update_pqrsf_priority", new_callable=AsyncMock)
async def test_update_pqrsf_priority(mock_update, client):
    """PUT /api/pqrsf/{id}/priority debe actualizar la prioridad."""
    item_id = uuid.uuid4()
    updated = make_submission(id=item_id, priority="high")
    mock_update.return_value = updated

    resp = await client.put(f"/api/pqrsf/{item_id}/priority", json={"priority": "high"})
    assert resp.status_code == 200, resp.text
    assert resp.json()["priority"] == "high"


@pytest.mark.asyncio
@patch("app.services.pqrsf.delete_pqrsf", new_callable=AsyncMock)
async def test_delete_pqrsf(mock_delete, client):
    """DELETE /api/pqrsf/{id} debe eliminar la PQRSF."""
    item_id = uuid.uuid4()
    mock_delete.return_value = True

    resp = await client.delete(f"/api/pqrsf/{item_id}")
    assert resp.status_code == 204


@pytest.mark.asyncio
@patch("app.services.pqrsf.delete_pqrsf", new_callable=AsyncMock)
async def test_delete_pqrsf_not_found(mock_delete, client):
    """DELETE /api/pqrsf/{id} inexistente debe retornar 404."""
    mock_delete.return_value = False

    resp = await client.delete(f"/api/pqrsf/{uuid.uuid4()}")
    assert resp.status_code == 404