# -*- coding: utf-8 -*-
"""Tests de la Incorporación Rápida (operador "solo evento" / ghost).

Reglas (ver ``services/quick_add.py`` y ``routers/events.py``):
- ``admin``/``superadmin``/``checkin`` (rol Check-in e Indumentaria) pueden
  usar POST /{event_id}/quick-add desde el panel de staff.
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

from app.models.events import Event, EventAssignment
from app.models.operators import Operator
from app.models.users import User
from app.services.auth import hash_password


async def _mk_user(db, doc, user_type, is_active=True, doc_type="CC"):
    u = User(
        id=uuid.uuid4(),
        email=f"{doc}@qa.test" if is_active else None,
        password_hash=hash_password("secreto123"),
        first_name="Usr",
        last_name=doc,
        user_type=user_type,
        document_type=doc_type,
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


@pytest.mark.asyncio
async def test_quick_add_by_checkin_role(client, qa_env, db):
    """El rol checkin (Check-in e Indumentaria) también puede incorporar rápido."""
    await _mk_user(db, "80003", "checkin")
    await db.commit()
    checkin_token = await _login(client, "80003")

    res = await client.post(
        f"/api/events/{qa_env['event_id']}/quick-add",
        json=_payload("999005"),
        headers={"Authorization": f"Bearer {checkin_token}"},
    )
    assert res.status_code == 201, res.text
    d = res.json()
    assert d["mode"] == "ghost"
    assert d["status"] == "confirmed"


@pytest.mark.asyncio
async def test_quick_add_imported_cedula_type(client, qa_env, db):
    """Operador importado por Excel con tipo 'CEDULA' + quick-add con 'CC'
    -> 201 mode=existing (antes: 500 por violar UNIQUE del documento)."""
    imported_user = await _mk_user(db, "80010", "operator", doc_type="CEDULA")
    imported_op = Operator(user_id=imported_user.id, event_only=False)
    db.add(imported_op)
    await db.commit()

    res = await client.post(
        f"/api/events/{qa_env['event_id']}/quick-add",
        json=_payload("80010"),  # envia document_type="CC"
        headers={"Authorization": f"Bearer {qa_env['admin_token']}"},
    )
    assert res.status_code == 201, res.text
    assert res.json()["mode"] == "existing"


@pytest.mark.asyncio
async def test_quick_add_existing_doc_different_type(client, qa_env, db):
    """Operador guardado como CE + quick-add con CC -> 201 existing."""
    ce_user = await _mk_user(db, "80011", "operator", doc_type="CE")
    ce_op = Operator(user_id=ce_user.id, event_only=False)
    db.add(ce_op)
    await db.commit()

    payload = _payload("80011")
    payload["document_type"] = "CC"
    res = await client.post(
        f"/api/events/{qa_env['event_id']}/quick-add",
        json=payload,
        headers={"Authorization": f"Bearer {qa_env['admin_token']}"},
    )
    assert res.status_code == 201, res.text
    assert res.json()["mode"] == "existing"


@pytest.mark.asyncio
async def test_quick_add_passport_type_mismatch(client, qa_env, db):
    """Operador guardado como PA (importador Excel) + quick-add con PP
    -> 201 existing (antes: 500)."""
    pa_user = await _mk_user(db, "80012", "operator", doc_type="PA")
    pa_op = Operator(user_id=pa_user.id, event_only=False)
    db.add(pa_op)
    await db.commit()

    payload = _payload("80012")
    payload["document_type"] = "PP"
    res = await client.post(
        f"/api/events/{qa_env['event_id']}/quick-add",
        json=payload,
        headers={"Authorization": f"Bearer {qa_env['admin_token']}"},
    )
    assert res.status_code == 201, res.text
    assert res.json()["mode"] == "existing"


@pytest.mark.asyncio
async def test_quick_add_long_admin_name(client, qa_env, db):
    """admitted_by con nombre de admin > 100 chars -> 201 y truncado a <=100
    (regresion: antes [:200] sobre columna String(100) -> DataError -> 500)."""
    from sqlalchemy import select
    long_admin = User(
        id=uuid.uuid4(),
        email="longadmin@qa.test",
        password_hash=hash_password("secreto123"),
        first_name="Nombre" * 12,   # 72 chars
        last_name="Apellido" * 10,  # 80 chars
        user_type="admin",
        document_type="CC",
        document_number="80013",
        is_verified=True,
        is_approved=True,
        is_active=True,
    )
    db.add(long_admin)
    await db.commit()
    token = await _login(client, "80013")

    res = await client.post(
        f"/api/events/{qa_env['event_id']}/quick-add",
        json=_payload("999006"),
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 201, res.text

    row = await db.execute(
        select(EventAssignment).where(
            EventAssignment.id == uuid.UUID(res.json()["assignment_id"])
        )
    )
    assignment = row.scalar_one()
    assert assignment.admitted_by is not None
    assert len(assignment.admitted_by) <= 100
