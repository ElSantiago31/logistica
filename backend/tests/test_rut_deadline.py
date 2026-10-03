# -*- coding: utf-8 -*-
"""Tests del RUT opcional con plazo de gracia (rut_deadline_at).

Cubre:
- Propiedades del modelo: rut_blocked / rut_days_remaining.
- Asignación a eventos bloqueada cuando el plazo venció (aparece en
  ``unavailable`` con reason explicativo) y permitida mientras el plazo
  está vigente o el RUT ya fue cargado.
- Subida self-service POST /api/operators/me/rut: valida PDF, guarda el
  archivo, limpia el deadline y desbloquea la asignación.
- GET /api/operators/me/profile expone has_rut / rut_days_remaining.
"""
import uuid
from datetime import datetime, timedelta, timezone

import pytest
import fitz
from httpx import AsyncClient, ASGITransport

from app.main import app as fastapi_app
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.events import Event, EventStaffNeed
from app.models.operators import Operator
from app.models.roles import Role
from app.models.users import User
from app.services.auth import hash_password

UTC = timezone.utc


def _make_pdf_bytes(text: str = "RUT de prueba") -> bytes:
    """PDF mínimo y válido generado en memoria (pasa _PDF_MAGIC y fitz)."""
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), text)
    data = doc.tobytes()
    doc.close()
    return data


async def _mk_user(db, email, doc, user_type="operator"):
    u = User(
        id=uuid.uuid4(),
        email=email,
        password_hash=hash_password("password"),
        first_name="Op",
        last_name=email.split("@")[0].capitalize(),
        user_type=user_type,
        document_type="CC",
        document_number=doc,
        is_verified=True,
        is_approved=True,
    )
    db.add(u)
    await db.flush()
    return u


async def _mk_operator(db, user_id, **kw):
    o = Operator(user_id=user_id, city="Bogota", **kw)
    db.add(o)
    await db.flush()
    return o


# ────────────────────────── Modelo ──────────────────────────

class TestRutModelProperties:
    def test_no_deadline_no_block(self):
        op = Operator(user_id=uuid.uuid4())
        assert op.rut_blocked is False
        assert op.rut_days_remaining is None

    def test_deadline_future_not_blocked(self):
        op = Operator(
            user_id=uuid.uuid4(),
            rut_deadline_at=datetime.now(UTC) + timedelta(days=10),
        )
        assert op.rut_blocked is False
        assert op.rut_days_remaining == 10

    def test_deadline_past_blocked_zero_days(self):
        op = Operator(
            user_id=uuid.uuid4(),
            rut_deadline_at=datetime.now(UTC) - timedelta(days=1),
        )
        assert op.rut_blocked is True
        assert op.rut_days_remaining == 0

    def test_rut_uploaded_ignores_deadline(self):
        op = Operator(
            user_id=uuid.uuid4(),
            rut_path="/static/rut/x.pdf",
            rut_deadline_at=datetime.now(UTC) - timedelta(days=30),
        )
        assert op.rut_blocked is False
        assert op.rut_days_remaining is None


# ──────────────────── Asignación de eventos ────────────────────

@pytest.fixture
async def rut_env(db: AsyncSession):
    """Admin + evento + rol; operadores se crean por test según su estado RUT."""
    event = Event(
        id=uuid.uuid4(),
        name="Evento RUT Deadline",
        start_date=datetime.now(UTC) + timedelta(days=30),
        end_date=datetime.now(UTC) + timedelta(days=30, hours=8),
        location="Plaza",
        status="published",
    )
    db.add(event)
    await db.flush()

    admin = await _mk_user(db, "admin.rut@test.com", "77001", "admin")
    role = Role(name="Rut Rol", slug=f"rut-{uuid.uuid4().hex[:6]}", hierarchy_level=5)
    db.add(role)
    await db.flush()
    db.add(EventStaffNeed(
        event_id=event.id, role_id=role.id,
        quantity_needed=10, quantity_confirmed=0,
    ))
    await db.commit()

    async with AsyncClient(
        transport=ASGITransport(app=fastapi_app),
        base_url="http://test",
    ) as ac:
        resp = await ac.post(
            "/api/auth/login",
            json={"document_number": "77001", "password": "password"},
        )
    token = resp.json()["access_token"]

    return {"event_id": str(event.id), "role_id": str(role.id), "token": token}


async def _assign(client, env, operator_id):
    return await client.post(
        f"/api/events/{env['event_id']}/assign",
        json={"operator_ids": [str(operator_id)], "role_id": env["role_id"]},
        headers={"Authorization": f"Bearer {env['token']}"},
    )


@pytest.mark.asyncio
async def test_assign_blocked_when_deadline_expired(db, client, rut_env):
    """Plazo vencido: el operador va a `unavailable` y NO se crea asignación."""
    u = await _mk_user(db, "blocked.rut@test.com", "77101")
    op = await _mk_operator(db, u.id, rut_deadline_at=datetime.now(UTC) - timedelta(days=2))
    await db.commit()

    resp = await _assign(client, rut_env, op.id)
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["assignments"]) == 0, "No debe crearse la asignación"
    assert len(body["unavailable"]) == 1
    assert "RUT" in body["unavailable"][0]["reason"]


@pytest.mark.asyncio
async def test_assign_allowed_when_deadline_active(db, client, rut_env):
    """Plazo vigente (15 días): la asignación se crea normalmente."""
    u = await _mk_user(db, "pending.rut@test.com", "77102")
    op = await _mk_operator(db, u.id, rut_deadline_at=datetime.now(UTC) + timedelta(days=15))
    await db.commit()

    resp = await _assign(client, rut_env, op.id)
    assert resp.status_code == 200
    assert len(resp.json()["assignments"]) == 1
    assert len(resp.json()["unavailable"]) == 0


@pytest.mark.asyncio
async def test_assign_allowed_without_deadline_legacy(db, client, rut_env):
    """Operador legacy sin deadline (col NULL): no se bloquea."""
    u = await _mk_user(db, "legacy.rut@test.com", "77103")
    op = await _mk_operator(db, u.id)  # sin rut_deadline_at
    await db.commit()

    resp = await _assign(client, rut_env, op.id)
    assert resp.status_code == 200
    assert len(resp.json()["assignments"]) == 1


# ──────────────── Subida self-service POST /me/rut ────────────────

@pytest.fixture
def rut_storage(tmp_path, monkeypatch):
    """Aísla los archivos RUT generados en tmp_path."""
    monkeypatch.setattr(settings, "RUT_DIR", str(tmp_path))
    return tmp_path


@pytest.mark.asyncio
async def test_upload_rut_unblocks_operator(db, client, rut_env, rut_storage):
    """Flujo completo: bloqueado → sube RUT → desbloqueado."""
    u = await _mk_user(db, "flow.rut@test.com", "77104")
    op = await _mk_operator(db, u.id, rut_deadline_at=datetime.now(UTC) - timedelta(days=1))
    await db.commit()

    resp = await _assign(client, rut_env, op.id)
    assert len(resp.json()["assignments"]) == 0, "Debe estar bloqueado al inicio"

    # Login como el operador
    login = await client.post("/api/auth/login", json={
        "document_number": "77104", "password": "password",
    })
    op_token = login.json()["access_token"]

    # 1. Rechaza archivo que no es PDF
    bad = await client.post(
        "/api/operators/me/rut",
        files={"rut": ("rut.txt", b"no es un pdf", "text/plain")},
        headers={"Authorization": f"Bearer {op_token}"},
    )
    assert bad.status_code == 400

    # 2. Sube PDF válido
    pdf = _make_pdf_bytes()
    up = await client.post(
        "/api/operators/me/rut",
        files={"rut": ("rut.pdf", pdf, "application/pdf")},
        headers={"Authorization": f"Bearer {op_token}"},
    )
    assert up.status_code == 200, up.text
    body = up.json()
    assert body["has_rut"] is True
    assert body["rut_days_remaining"] is None

    # 3. El perfil refleja el estado
    prof = await client.get(
        "/api/operators/me/profile",
        headers={"Authorization": f"Bearer {op_token}"},
    )
    assert prof.status_code == 200
    pdata = prof.json()["operator"]
    assert pdata["has_rut"] is True
    assert pdata["rut_days_remaining"] is None
    assert pdata["rut_deadline_at"] is None

    # 4. La asignación queda desbloqueada
    resp = await _assign(client, rut_env, op.id)
    assert resp.status_code == 200
    assert len(resp.json()["assignments"]) == 1, "Debe poder asignarse tras subir RUT"


@pytest.mark.asyncio
async def test_upload_rut_requires_operator_role(db, client, rut_env, rut_storage):
    """Un admin no puede usar el endpoint self-service."""
    pdf = _make_pdf_bytes()
    resp = await client.post(
        "/api/operators/me/rut",
        files={"rut": ("rut.pdf", pdf, "application/pdf")},
        headers={"Authorization": f"Bearer {rut_env['token']}"},
    )
    assert resp.status_code == 403