# -*- coding: utf-8 -*-
"""Test de regresión: sobre-invitación por rol.

Escenario real: un evento necesita solo 1 operador de un rol, pero NO todos
los invitados aceptan. El admin debe poder asignar/invitar MÁS operadores
que quantity_needed para cubrir rechazos.

- El backend NUNCA debe bloquear la asignación por exceder el plan del rol
  (el cupo de rol es informativo; el cierre real son las confirmaciones).
- Regresión del fix frontend: el botón "Asignar" ya no se deshabilita por
  exceder quantity_needed - quantity_confirmed (event_detail.html).
"""
import uuid
from datetime import datetime, timezone

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.events import Event, EventStaffNeed
from app.models.roles import Role
from app.models.operators import Operator
from app.models.users import User
from app.services.auth import hash_password


async def _create_user(db, email, doc, user_type="admin"):
    u = User(
        id=uuid.uuid4(),
        email=email,
        password_hash=hash_password("password"),
        first_name="Test",
        last_name=email.split("@")[0],
        user_type=user_type,
        document_type="CC",
        document_number=doc,
        is_verified=True,
        is_approved=True,
    )
    db.add(u)
    await db.flush()
    return u


async def _create_operator(db, user_id):
    o = Operator(user_id=user_id, city="Bogota")
    db.add(o)
    await db.flush()
    return o


@pytest.fixture
async def overinvite_env(db: AsyncSession, client: AsyncClient):
    """Evento con staff_need de 1 Logística + 3 operadores disponibles."""
    event = Event(
        id=uuid.uuid4(),
        name="Evento Sobre-Invitacion",
        start_date=datetime(2026, 9, 5, 8, 0, 0, tzinfo=timezone.utc),
        end_date=datetime(2026, 9, 5, 18, 0, 0, tzinfo=timezone.utc),
        location="Plaza",
        status="published",
    )
    db.add(event)
    await db.flush()

    admin = await _create_user(db, "admin.oi@test.com", "91001", "admin")
    role = Role(name="Logistica Overinvite", slug="log-oi", hierarchy_level=5)
    db.add(role)
    await db.flush()

    # El plan pide SOLO 1 operador de este rol
    db.add(EventStaffNeed(
        event_id=event.id, role_id=role.id,
        quantity_needed=1, quantity_confirmed=0,
    ))

    ops = []
    for i in range(3):
        u = await _create_user(db, f"op{i}.oi@test.com", f"9100{i + 2}", "operator")
        ops.append(await _create_operator(db, u.id))
    await db.commit()

    resp = await client.post("/api/auth/login", json={
        "document_number": "91001", "password": "password",
    })
    token = resp.json()["access_token"]

    return {
        "event_id": str(event.id),
        "role_id": str(role.id),
        "operator_ids": [str(o.id) for o in ops],
        "token": token,
        "admin": admin,
    }


@pytest.mark.asyncio
async def test_assign_more_than_quantity_needed(client: AsyncClient, overinvite_env):
    """Asignar 3 operadores a un rol que pide 1: debe crear las 3 asignaciones."""
    env = overinvite_env
    resp = await client.post(
        f"/api/events/{env['event_id']}/assign",
        json={
            "operator_ids": env["operator_ids"],
            "role_id": env["role_id"],
        },
        headers={"Authorization": f"Bearer {env['token']}"},
    )
    assert resp.status_code == 200, resp.text

    # Verificar que quedaron las 3 asignaciones en estado invited
    resp = await client.get(
        f"/api/events/{env['event_id']}/assignments",
        headers={"Authorization": f"Bearer {env['token']}"},
    )
    assert resp.status_code == 200
    assignments = resp.json()
    assert len(assignments) == 3, (
        f"Se esperaban 3 asignaciones (sobre-invitacion), hay {len(assignments)}"
    )
    statuses = {a["status"] for a in assignments}
    assert statuses == {"invited"}, f"Estados inesperados: {statuses}"


@pytest.mark.asyncio
async def test_confirmed_count_not_inflated_by_invited(client: AsyncClient, overinvite_env):
    """Sobre-invitar no debe inflar quantity_confirmed: sigue en 0 hasta confirmar."""
    env = overinvite_env
    resp = await client.post(
        f"/api/events/{env['event_id']}/assign",
        json={"operator_ids": env["operator_ids"], "role_id": env["role_id"]},
        headers={"Authorization": f"Bearer {env['token']}"},
    )
    assert resp.status_code == 200

    resp = await client.get(
        f"/api/events/{env['event_id']}",
        headers={"Authorization": f"Bearer {env['token']}"},
    )
    assert resp.status_code == 200
    ev = resp.json()
    needs = ev.get("staff_needs") or []
    assert needs, "El evento debe tener su staff_need"
    assert needs[0]["quantity_needed"] == 1
    # Los invitados NO cuentan como confirmados: el plan sigue en 0/1
    assert needs[0]["quantity_confirmed"] == 0