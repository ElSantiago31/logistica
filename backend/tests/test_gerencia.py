# -*- coding: utf-8 -*-
"""Tests del rol "gerencia" (vista 360 de eventos, solo lectura).

FASE 1: alta del rol y login. FASE 2 ampliará con los endpoints de
monitoreo (/api/monitoring/...).
"""
import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.users import User
from app.services.auth import hash_password


async def _create_staff(db: AsyncSession, doc: str, user_type: str) -> User:
    u = User(
        id=uuid.uuid4(),
        email=None,
        password_hash=hash_password("password"),
        first_name="Staff",
        last_name=user_type.title(),
        user_type=user_type,
        document_type="CC",
        document_number=doc,
        is_verified=True,
        is_approved=True,
        is_active=True,
    )
    db.add(u)
    await db.flush()
    return u


async def _login(client: AsyncClient, doc: str) -> str:
    resp = await client.post("/api/auth/login", json={
        "document_number": doc, "password": "password",
    })
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


@pytest.fixture
async def gerencia_env(db: AsyncSession, client: AsyncClient):
    superadmin = await _create_staff(db, "99001", "superadmin")
    gerencia = await _create_staff(db, "99002", "gerencia")
    await db.commit()
    return {"superadmin": superadmin, "gerencia": gerencia}


@pytest.mark.asyncio
async def test_gerencia_can_login(client: AsyncClient, gerencia_env):
    """El rol gerencia inicia sesión normalmente y recibe su user_type."""
    resp = await client.post("/api/auth/login", json={
        "document_number": "99002", "password": "password",
    })
    assert resp.status_code == 200, resp.text
    assert resp.json()["user"]["user_type"] == "gerencia"


@pytest.mark.asyncio
async def test_gerencia_cannot_create_admins(client: AsyncClient, gerencia_env):
    """Gerencia NO puede crear usuarios (no es superadmin ni admin)."""
    token = await _login(client, "99002")
    resp = await client.post(
        "/api/auth/admins",
        json={
            "first_name": "X", "last_name": "Y",
            "document_number": "99999", "password": "secret1",
            "user_type": "admin",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403, resp.text


@pytest.mark.asyncio
async def test_superadmin_creates_gerencia(client: AsyncClient, gerencia_env):
    """Superadmin crea un usuario gerencia vía /api/auth/admins."""
    token = await _login(client, "99001")
    resp = await client.post(
        "/api/auth/admins",
        json={
            "first_name": "Dueno", "last_name": "Empresa",
            "document_number": "99003", "password": "secret1",
            "user_type": "gerencia",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201, resp.text

    # Aparece en el listado de staff con su rol
    resp = await client.get("/api/auth/admins", headers={
        "Authorization": f"Bearer {token}",
    })
    assert resp.status_code == 200
    types = [a["user_type"] for a in resp.json()]
    assert "gerencia" in types


@pytest.mark.asyncio
async def test_admin_cannot_create_gerencia(client: AsyncClient, db: AsyncSession):
    """Un admin NO puede crear gerencia (solo superadmin)."""
    await _create_staff(db, "99010", "admin")
    await db.commit()
    token = await _login(client, "99010")
    resp = await client.post(
        "/api/auth/admins",
        json={
            "first_name": "No", "last_name": "Debe",
            "document_number": "99011", "password": "secret1",
            "user_type": "gerencia",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201, resp.text  # crea, pero colapsa a checkin
    # Verificar el colapso de rol en el listado
    resp = await client.get("/api/auth/admins", headers={
        "Authorization": f"Bearer {token}",
    })
    created = [a for a in resp.json() if a["document_number"] == "99011"]
    assert created and created[0]["user_type"] == "checkin"


# =====================================================================
# FASE 2 — API de monitoreo (/api/monitoring/...)
# =====================================================================
from datetime import datetime, timezone

from app.models.events import Event, EventStaffNeed, EventAssignment, EventCoordinatorQuota
from app.models.roles import Role
from app.models.operators import Operator


@pytest.fixture
async def monitoring_env(db: AsyncSession, client: AsyncClient):
    """Evento publicado con 1 need, 3 asignaciones (2 checked_in, 1 confirmed)."""
    event = Event(
        id=uuid.uuid4(),
        name="Evento Gerencia 360",
        start_date=datetime(2026, 9, 10, 8, 0, 0, tzinfo=timezone.utc),
        end_date=datetime(2026, 9, 10, 18, 0, 0, tzinfo=timezone.utc),
        location="Plaza Mayor",
        status="published",
        client_name="Cliente SAC",
    )
    db.add(event)
    await db.flush()

    role = Role(name="Logistica Gerencia", slug="log-ger", hierarchy_level=5)
    db.add(role)
    await db.flush()

    db.add(EventStaffNeed(
        event_id=event.id, role_id=role.id,
        quantity_needed=3, quantity_confirmed=3, stage="evento",
    ))
    db.add(EventCoordinatorQuota(
        event_id=event.id, coordinator="JUAN", quota=10, stage="evento",
    ))

    for i, st in enumerate(["checked_in", "checked_in", "confirmed"]):
        u = User(
            id=uuid.uuid4(), email=None,
            password_hash=hash_password("password"),
            first_name="Op", last_name=f"G{i}",
            user_type="operator", document_type="CC",
            document_number=f"9910{i}", is_verified=True, is_approved=True,
        )
        db.add(u)
        await db.flush()
        op = Operator(user_id=u.id, city="Bogota")
        db.add(op)
        await db.flush()
        db.add(EventAssignment(
            event_id=event.id, operator_id=op.id, role_id=role.id,
            status=st, programmed_by="JUAN",
            admitted_by="JUAN" if st == "checked_in" else None,
        ))
    await db.commit()

    return {"event_id": str(event.id)}


@pytest.mark.asyncio
async def test_monitoring_overview_200(client: AsyncClient, monitoring_env, gerencia_env):
    """Caso 1: gerencia ve el overview 360 con estructura completa."""
    tok = await _login(client, "99002")  # gerencia del fixture de FASE 1
    resp = await client.get(
        f"/api/monitoring/events/{monitoring_env['event_id']}/overview",
        headers={"Authorization": f"Bearer {tok}"},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert set(data) >= {"event", "totals", "by_role", "by_coordinator", "by_stage", "recent_checkins", "updated_at"}
    t = data["totals"]
    assert t["assigned"] == 3
    assert t["confirmed"] == 1
    assert t["checked_in"] == 2
    assert t["pending_checkin"] == 1
    assert t["checkin_pct"] == 200.0
    assert data["event"]["client_name"] == "Cliente SAC"
    assert len(data["by_role"]) == 1
    assert data["by_role"][0]["needed"] == 3
    assert data["by_stage"][0]["stage"] == "evento"


@pytest.mark.asyncio
async def test_monitoring_events_list_200(client: AsyncClient, monitoring_env, gerencia_env):
    """Caso 2: gerencia lista TODOS los eventos vía /api/monitoring/events."""
    tok = await _login(client, "99002")
    resp = await client.get(
        "/api/monitoring/events",
        headers={"Authorization": f"Bearer {tok}"},
    )
    assert resp.status_code == 200, resp.text
    items = resp.json()
    assert any(i["name"] == "Evento Gerencia 360" for i in items)
    ev = next(i for i in items if i["name"] == "Evento Gerencia 360")
    assert ev["confirmed"] == 1 and ev["checked_in"] == 2


@pytest.mark.asyncio
async def test_gerencia_cannot_write_events(client: AsyncClient, monitoring_env, gerencia_env):
    """Caso 3: gerencia recibe 403 en POST/PUT/DELETE de eventos."""
    tok = await _login(client, "99002")
    headers = {"Authorization": f"Bearer {tok}"}
    base = {
        "name": "XXX", "location": "YYY",
        "start_date": "2026-09-10T08:00:00Z", "end_date": "2026-09-10T18:00:00Z",
    }
    r1 = await client.post("/api/events/", json=base, headers=headers)
    assert r1.status_code == 403, r1.text
    r2 = await client.put(
        f"/api/events/{monitoring_env['event_id']}", json=base, headers=headers,
    )
    assert r2.status_code == 403, r2.text
    r3 = await client.request(
        "DELETE", f"/api/events/{monitoring_env['event_id']}",
        json={"password": "password"}, headers=headers,
    )
    assert r3.status_code == 403, r3.text


@pytest.mark.asyncio
async def test_operator_cannot_view_overview(client: AsyncClient, monitoring_env, db: AsyncSession):
    """Caso 6: un operador SIN asignación al evento no ve el overview."""
    u = User(
        id=uuid.uuid4(), email=None,
        password_hash=hash_password("password"),
        first_name="Op", last_name="Fuera",
        user_type="operator", document_type="CC",
        document_number="99199", is_verified=True, is_approved=True,
    )
    db.add(u)
    await db.flush()
    db.add(Operator(user_id=u.id, city="Bogota"))
    await db.commit()

    tok = await _login(client, "99199")
    resp = await client.get(
        f"/api/monitoring/events/{monitoring_env['event_id']}/overview",
        headers={"Authorization": f"Bearer {tok}"},
    )
    assert resp.status_code == 403, resp.text
