# -*- coding: utf-8 -*-
"""Tests de la Incorporación Rápida (operador "solo evento" / ghost).

Reglas (ver ``services/quick_add.py`` y ``routers/events.py``):
- ``admin``/``superadmin`` pueden usar POST /{event_id}/quick-add.
- Documento nuevo → crea usuario fantasma (is_active=False, email NULL,
  operator.event_only=True) y asignación status=confirmed (mode="ghost").
- Documento de operador REAL → reutiliza existente (mode="existing").
- Documento ya asignado a ESTE evento → 409.
- DELETE /assignments/{id} purga el ghost si queda sin asignaciones activas.
- DELETE del evento purga los ghosts del evento.
- El ghost NO puede iniciar sesión (authenticate_user rechaza is_active=False).
"""
import uuid
from datetime import datetime, timezone

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.events import Event
from app.models.operators import Operator
from app.models.users import User
from app.services.auth import hash_password


async def _mk_user(db, doc, user_type, is_active=True):
    u = User(
        id=uuid.uuid4(),
        email=f"{doc}@qa.test" if is_active else None,
        password_hash=hash_password("secreto123"),
        first_name="Usr",
        last_name=doc,
        user_type=user_type,
        document_type="CC",
        document_number=doc,
        is_verified=True,
        is_approved=user_type != "operator",
        is_active=is_active,
    )
    db.add(u)
    await db.flush()
    return u


async def _login(client, doc):
    resp = await client.post("/api/auth/login", json={
        "document_number": doc, "password": "secreto123",
    })
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


@pytest.fixture
async def qa_env(db: AsyncSession, client: AsyncClient):
    event = Event(
        id=uuid.uuid4(),
        name="Evento Quick Add",
        start_date=datetime(2026, 9, 20, 8, 0, 0, tzinfo=timezone.utc),
        end_date=datetime(2026, 9, 20, 18, 0, 0, tzinfo=timezone.utc),
        location="Plaza Mayor",
        status="published",
    )
    db.add(event)
    admin = await _mk_user(db, "80001", "admin")
    # Operador real (registrado, activo) para probar mode="existing"
    real_user = await _mk_user(db, "80002", "operator")
    real_op = Operator(user_id=real_user.id, event_only=False)
    db.add(real_op)
    await db.commit()

    return {
        "event_id": str(event.id),
        "admin_token": await _login(client, "80001"),
        "real_doc": "80002",
    }


def _payload(doc):
    return {
        "primer_nombre": "Juan",
        "primer_apellido": "Pérez",
        "document_type": "CC",
        "document_number": doc,
    }


@pytest.mark.asyncio
async def test_quick_add_creates_ghost(client, qa_env):
    """Documento nuevo → mode=ghost, usuario inactivo, event_only=True."""
    res = await client.post(
        f"/api/events/{qa_env['event_id']}/quick-add",
        json=_payload("999001"),
        headers={"Authorization": f"Bearer {qa_env['admin_token']}"},
    )
    assert res.status_code == 201, res.text
    d = res.json()
    assert d["mode"] == "ghost"
    assert d["status"] == "confirmed"
    assert d["full_name"].startswith("Juan")

    # El usuario fantasma no puede iniciar sesión
    login = await client.post("/api/auth/login", json={
        "document_number": "999001", "password": "secreto123",
    })
    assert login.status_code in (401, 403)


@pytest.mark.asyncio
async def test_quick_add_reuses_real_operator(client, qa_env):
    """Documento de operador real → mode=existing, sin crear ghost."""
    res = await client.post(
        f"/api/events/{qa_env['event_id']}/quick-add",
        json=_payload(qa_env["real_doc"]),
        headers={"Authorization": f"Bearer {qa_env['admin_token']}"},
    )
    assert res.status_code == 201, res.text
    assert res.json()["mode"] == "existing"


@pytest.mark.asyncio
async def test_quick_add_duplicate_conflict(client, qa_env):
    """Mismo documento dos veces en el mismo evento → 409 la segunda."""
    url = f"/api/events/{qa_env['event_id']}/quick-add"
    hdrs = {"Authorization": f"Bearer {qa_env['admin_token']}"}
    first = await client.post(url, json=_payload("999002"), headers=hdrs)
    assert first.status_code == 201
    dup = await client.post(url, json=_payload("999002"), headers=hdrs)
    assert dup.status_code == 409


@pytest.mark.asyncio
async def test_remove_assignment_purges_ghost(client, qa_env, db):
    """Eliminar la asignación del ghost purga operador y usuario fantasma."""
    hdrs = {"Authorization": f"Bearer {qa_env['admin_token']}"}
    res = await client.post(
        f"/api/events/{qa_env['event_id']}/quick-add",
        json=_payload("999003"), headers=hdrs,
    )
    assert res.status_code == 201
    assignment_id = res.json()["assignment_id"]

    # Eliminar la asignación
    res2 = await client.delete(
        f"/api/events/assignments/{assignment_id}", headers=hdrs,
    )
    assert res2.status_code == 200, res2.text

    # El ghost debe haber sido purgado (operador y usuario desaparecen)
    user_id = res.json()["user_id"]
    from sqlalchemy import select
    gone = await db.execute(select(User).where(User.id == uuid.UUID(user_id)))
    assert gone.scalar_one_or_none() is None


@pytest.mark.asyncio
async def test_quick_add_requires_admin(client, qa_env):
    """Sin token → 401/403."""
    res = await client.post(
        f"/api/events/{qa_env['event_id']}/quick-add",
        json=_payload("999004"),
    )
    assert res.status_code in (401, 403)