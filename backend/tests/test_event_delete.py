# -*- coding: utf-8 -*-
"""Tests de eliminación de eventos con confirmación por contraseña.

Reglas (ver router ``events.delete_event``):
- Solo ``superadmin`` puede eliminar eventos.
- Debe enviar su contraseña de acceso en el body; si es incorrecta, 403.
- ``admin`` recibe 403 aunque envíe su contraseña correcta.
- Tras eliminar, GET del evento devuelve 404.
"""
import uuid
from datetime import datetime, timezone

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.events import Event
from app.models.users import User
from app.services.auth import hash_password


async def _mk_user(db, doc, user_type):
    u = User(
        id=uuid.uuid4(),
        email=f"{doc}@del.test",
        password_hash=hash_password("secreto123"),
        first_name="Del",
        last_name=user_type,
        user_type=user_type,
        document_type="CC",
        document_number=doc,
        is_verified=True,
        is_approved=True,
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
async def delete_env(db: AsyncSession, client: AsyncClient):
    event = Event(
        id=uuid.uuid4(),
        name="Evento a Eliminar",
        start_date=datetime(2026, 9, 20, 8, 0, 0, tzinfo=timezone.utc),
        end_date=datetime(2026, 9, 20, 18, 0, 0, tzinfo=timezone.utc),
        location="Plaza Mayor",
        status="draft",
    )
    db.add(event)
    superadmin = await _mk_user(db, "70001", "superadmin")
    admin = await _mk_user(db, "70002", "admin")
    await db.commit()

    return {
        "event_id": str(event.id),
        "super_token": await _login(client, "70001"),
        "admin_token": await _login(client, "70002"),
    }


@pytest.mark.asyncio
async def test_superadmin_deletes_with_correct_password(client, delete_env):
    """Superadmin + contraseña correcta -> 200 y evento eliminado."""
    res = await client.request(
        "DELETE",
        f"/api/events/{delete_env['event_id']}",
        json={"password": "secreto123"},
        headers={"Authorization": f"Bearer {delete_env['super_token']}"},
    )
    assert res.status_code == 200
    assert res.json()["message"] == "Evento eliminado"

    # Verificar que ya no existe
    res2 = await client.get(
        f"/api/events/{delete_env['event_id']}",
        headers={"Authorization": f"Bearer {delete_env['super_token']}"},
    )
    assert res2.status_code == 404


@pytest.mark.asyncio
async def test_wrong_password_rejected(client, delete_env):
    """Superadmin + contraseña INCORRECTA -> 403 y evento sigue existiendo."""
    res = await client.request(
        "DELETE",
        f"/api/events/{delete_env['event_id']}",
        json={"password": "incorrecta"},
        headers={"Authorization": f"Bearer {delete_env['super_token']}"},
    )
    assert res.status_code == 403

    res2 = await client.get(
        f"/api/events/{delete_env['event_id']}",
        headers={"Authorization": f"Bearer {delete_env['super_token']}"},
    )
    assert res2.status_code == 200


@pytest.mark.asyncio
async def test_admin_cannot_delete_even_with_password(client, delete_env):
    """admin (no superadmin) recibe 403 aunque la contraseña sea correcta."""
    res = await client.request(
        "DELETE",
        f"/api/events/{delete_env['event_id']}",
        json={"password": "secreto123"},
        headers={"Authorization": f"Bearer {delete_env['admin_token']}"},
    )
    assert res.status_code == 403


@pytest.mark.asyncio
async def test_delete_without_body_rejected(client, delete_env):
    """DELETE sin body (sin contraseña) -> 422 (validación del schema)."""
    res = await client.request(
        "DELETE",
        f"/api/events/{delete_env['event_id']}",
        headers={"Authorization": f"Bearer {delete_env['super_token']}"},
    )
    assert res.status_code == 422
