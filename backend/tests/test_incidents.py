# -*- coding: utf-8 -*-
"""Tests del módulo ⚠️ Incidencias y Vetos (acceso staff de puerta).

Reglas (ver ``routers/incidents.py``):
- Roles base (superadmin/admin/checkin/intendencia): acceso completo al módulo.
- Operadores con EventStaffAssignment ACTIVA (staff_role checkin/intendencia):
  acceso acotado al evento de la asignación.
- Operadores sin staff: 403 en todo el módulo.
- Acciones destructivas (DELETE novedad, reactivar veto): solo
  superadmin/admin (``require_superadmin_or_admin``).
- GET /bans?event_id=... filtra vetos de operadores asignados a ese evento.
"""
import uuid
from datetime import datetime, timezone

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.events import Event, EventAssignment, EventStaffAssignment
from app.models.operators import Operator
from app.models.roles import Role
from app.models.users import User
from app.services.auth import hash_password


async def _mk_user(db, doc, user_type, is_approved=True):
    u = User(
        id=uuid.uuid4(),
        email=f"{doc}@inc.test",
        password_hash=hash_password("secreto123"),
        first_name="Usr",
        last_name=doc,
        user_type=user_type,
        document_type="CC",
        document_number=doc,
        is_verified=True,
        is_approved=is_approved,
        is_active=True,
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
async def inc_env(db: AsyncSession, client: AsyncClient):
    event = Event(
        id=uuid.uuid4(),
        name="Evento Incidencias",
        start_date=datetime(2026, 9, 25, 8, 0, 0, tzinfo=timezone.utc),
        end_date=datetime(2026, 9, 25, 18, 0, 0, tzinfo=timezone.utc),
        location="Plaza Mayor",
        status="published",
    )
    db.add(event)

    admin = await _mk_user(db, "70001", "admin")
    checkin = await _mk_user(db, "70002", "checkin")

    # Operador objetivo de las novedades (asignado al evento)
    target_user = await _mk_user(db, "70003", "operator")
    target_op = Operator(user_id=target_user.id, event_only=False)
    db.add(target_op)

    # Operador con asignación staff en el evento (user_type=operator)
    staff_user = await _mk_user(db, "70004", "operator")
    staff_op = Operator(user_id=staff_user.id, event_only=False)
    db.add(staff_op)

    # Operador SIN asignación staff (debe recibir 403)
    plain_user = await _mk_user(db, "70005", "operator")
    plain_op = Operator(user_id=plain_user.id, event_only=False)
    db.add(plain_op)

    await db.flush()

    role = Role(name="Operador Test", slug="op-test", hierarchy_level=5)
    db.add(role)
    await db.flush()

    db.add(EventAssignment(
        event_id=event.id, operator_id=target_op.id,
        status="confirmed", role_id=role.id,
    ))
    db.add(EventStaffAssignment(
        event_id=event.id, user_id=staff_user.id,
        staff_role="checkin", is_active=True,
    ))
    await db.commit()

    return {
        "event_id": str(event.id),
        "target_operator_id": str(target_op.id),
        "target_user_doc": "70003",
        "tokens": {
            "admin": await _login(client, "70001"),
            "checkin": await _login(client, "70002"),
            "staff": await _login(client, "70004"),
            "plain": await _login(client, "70005"),
        },
    }


def _incident_payload(env):
    return {
        "event_id": env["event_id"],
        "operator_id": env["target_operator_id"],
        "incident_type": "llegada_tarde",
        "description": "Llegó 20 minutos tarde",
    }


@pytest.mark.asyncio
async def test_checkin_role_can_list_and_create(client, inc_env):
    """El rol checkin (staff de puerta) consulta y registra novedades."""
    hdrs = {"Authorization": f"Bearer {inc_env['tokens']['checkin']}"}

    res = await client.get(
        f"/api/incidents?event_id={inc_env['event_id']}", headers=hdrs)
    assert res.status_code == 200, res.text

    res = await client.post(
        "/api/incidents", json=_incident_payload(inc_env), headers=hdrs)
    assert res.status_code == 201, res.text
    assert res.json()["incident_type"] == "llegada_tarde"


@pytest.mark.asyncio
async def test_operator_staff_assignment_can_create(client, inc_env):
    """Operador con EventStaffAssignment activa puede registrar novedades."""
    hdrs = {"Authorization": f"Bearer {inc_env['tokens']['staff']}"}
    res = await client.post(
        "/api/incidents", json=_incident_payload(inc_env), headers=hdrs)
    assert res.status_code == 201, res.text


@pytest.mark.asyncio
async def test_plain_operator_forbidden(client, inc_env):
    """Operador sin asignación staff recibe 403 en el módulo."""
    hdrs = {"Authorization": f"Bearer {inc_env['tokens']['plain']}"}
    res = await client.get(
        f"/api/incidents?event_id={inc_env['event_id']}", headers=hdrs)
    assert res.status_code == 403, res.text

    res = await client.post(
        "/api/incidents", json=_incident_payload(inc_env), headers=hdrs)
    assert res.status_code == 403, res.text


@pytest.mark.asyncio
async def test_checkin_cannot_delete_incident(client, inc_env):
    """DELETE novedad es destructivo: solo superadmin/admin."""
    hdrs_admin = {"Authorization": f"Bearer {inc_env['tokens']['admin']}"}
    res = await client.post(
        "/api/incidents", json=_incident_payload(inc_env), headers=hdrs_admin)
    assert res.status_code == 201, res.text
    inc_id = res.json()["id"]

    hdrs = {"Authorization": f"Bearer {inc_env['tokens']['checkin']}"}
    res = await client.delete(f"/api/incidents/{inc_id}", headers=hdrs)
    assert res.status_code == 403, res.text

    # Admin sí puede
    res = await client.delete(f"/api/incidents/{inc_id}", headers=hdrs_admin)
    assert res.status_code == 204, res.text


@pytest.mark.asyncio
async def test_bans_scoped_by_event_and_reactivate_admin_only(client, inc_env):
    """GET /bans?event_id filtra por operadores del evento; reactivar es
    solo para management."""
    hdrs_admin = {"Authorization": f"Bearer {inc_env['tokens']['admin']}"}
    hdrs_checkin = {"Authorization": f"Bearer {inc_env['tokens']['checkin']}"}

    # Vetar al operador asignado al evento
    res = await client.post("/api/incidents/bans", json={
        "operator_id": inc_env["target_operator_id"],
        "reason": "Comportamiento inadecuado",
        "event_id": inc_env["event_id"],
    }, headers=hdrs_admin)
    assert res.status_code == 201, res.text
    ban = res.json()
    assert ban["is_active"] is True

    # Scoped: el veto aparece para el evento
    res = await client.get(
        f"/api/incidents/bans?event_id={inc_env['event_id']}",
        headers=hdrs_checkin)
    assert res.status_code == 200, res.text
    docs = [b["operator_document"] for b in res.json()]
    assert "70003" in docs

    # Reactivar es destructivo: checkin recibe 403
    res = await client.post(
        f"/api/incidents/bans/reactivate?operator_id={inc_env['target_operator_id']}",
        json={"unban_reason": "prueba"}, headers=hdrs_checkin)
    assert res.status_code == 403, res.text

    # Admin sí puede reactivar
    res = await client.post(
        f"/api/incidents/bans/reactivate?operator_id={inc_env['target_operator_id']}",
        json={"unban_reason": "Segunda oportunidad"}, headers=hdrs_admin)
    assert res.status_code == 200, res.text
    assert res.json()["is_active"] is False