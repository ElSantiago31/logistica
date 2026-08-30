# -*- coding: utf-8 -*-
"""Tests del flujo de sobrecupo (force_overquota) en check-in, del CSV
de log de ingresos y del cambio de rol en check-in (ver docs/FASE4.x).
"""
import csv
import uuid
from datetime import datetime, timezone
from io import StringIO

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.events import Event, EventAssignment, EventCoordinatorQuota
from app.models.roles import Role
from app.models.sync import AttendanceLog
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


async def _create_operator(db, user_id, name="Op"):
    o = Operator(user_id=user_id, city="Bogota")
    db.add(o)
    await db.flush()
    return o


@pytest.fixture
async def overquota_env(db: AsyncSession, client: AsyncClient):
    """Evento con coordinador XIMENA quota=1 y 1 check-in ya registrado.

    El segundo check-in a XIMENA dispara QUOTA_FULL si no se fuerza.
    """
    event = Event(
        id=uuid.uuid4(),
        name="Evento Sobrecupo",
        start_date=datetime(2026, 8, 30, 8, 0, 0, tzinfo=timezone.utc),
        end_date=datetime(2026, 8, 30, 18, 0, 0, tzinfo=timezone.utc),
        location="Plaza",
        status="active",
    )
    db.add(event)
    await db.flush()

    admin = await _create_user(db, "admin.oq@test.com", "90001", "admin")
    u1 = await _create_user(db, "op1.oq@test.com", "90002", "operator")
    u2 = await _create_user(db, "op2.oq@test.com", "90003", "operator")
    o1 = await _create_operator(db, u1.id)
    o2 = await _create_operator(db, u2.id)

    db.add(EventCoordinatorQuota(
        event_id=event.id, coordinator="XIMENA", quota=1,
    ))
    # Roles para probar el cambio de rol en check-in
    r_brig = Role(name="Brigadista Test", slug="brig-test", hierarchy_level=5)
    r_log = Role(name="Logistica Test", slug="log-test", hierarchy_level=5)
    db.add_all([r_brig, r_log])
    await db.flush()
    a1 = EventAssignment(
        event_id=event.id, operator_id=o1.id, status="checked_in",
        admitted_by="XIMENA", role_id=r_brig.id,
    )
    db.add(a1)
    await db.flush()
    db.add(AttendanceLog(
        event_id=event.id, assignment_id=a1.id, operator_id=o1.id,
        check_in_time=datetime(2026, 8, 30, 8, 5, 0, tzinfo=timezone.utc),
        check_in_method="manual",
    ))
    u3 = await _create_user(db, "op3.oq@test.com", "90004", "operator")
    o3 = await _create_operator(db, u3.id)
    a3 = EventAssignment(
        event_id=event.id, operator_id=o3.id, status="checked_in",
        admitted_by="XIMENA",
    )
    db.add(a3)
    await db.flush()
    db.add(AttendanceLog(
        event_id=event.id, assignment_id=a3.id, operator_id=o3.id,
        check_in_time=datetime(2026, 8, 30, 9, 30, 0, tzinfo=timezone.utc),
        check_in_method="manual",
        notes="sobrecupo:XIMENA",
    ))
    db.add(EventAssignment(
        event_id=event.id, operator_id=o2.id, status="confirmed",
    ))
    await db.commit()

    # Login del admin (los fixtures de test_operators usan el mismo flujo)
    resp = await client.post("/api/auth/login", json={
        "document_number": "90001", "password": "password",
    })
    token = resp.json()["access_token"]

    return {
        "event_id": str(event.id),
        "assignment_id": None,  # se llena en el test tras consultar
        "token": token,
        "operator2": o2,
        "admin": admin,
        "role_logistica": r_log,
        "assignment_checked": a1,
    }


async def _get_pending_assignment_id(client, token, event_id):
    resp = await client.get(
        f"/api/sync/events/{event_id}/checkin-status",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200, resp.text
    for a in resp.json().get("assignments", []):
        if a.get("status") == "confirmed":
            return a["id"]
    raise AssertionError("No hay assignment confirmed en checkin-status")


@pytest.mark.asyncio
async def test_checkin_quota_full_rejected(client, overquota_env):
    """Sin force_overquota: cupo lleno -> 409 QUOTA_FULL con suggestions."""
    aid = await _get_pending_assignment_id(client, overquota_env["token"], overquota_env["event_id"])
    resp = await client.post(
        f"/api/sync/events/{overquota_env['event_id']}/check-in",
        headers={"Authorization": f"Bearer {overquota_env['token']}"},
        json={
            "assignment_id": aid,
            "operator_id": str(overquota_env["operator2"].id),
            "method": "manual",
            "coordinator": "XIMENA",
        },
    )
    assert resp.status_code == 409, resp.text
    det = resp.json()["detail"]
    assert det["error"] == "QUOTA_FULL"
    assert det["coordinator"] == "XIMENA"
    assert isinstance(det["suggestions"], list)


@pytest.mark.asyncio
async def test_checkin_force_overquota_succeeds(client, overquota_env):
    """Con force_overquota=true: el check-in pasa aunque el cupo este lleno."""
    aid = await _get_pending_assignment_id(client, overquota_env["token"], overquota_env["event_id"])
    resp = await client.post(
        f"/api/sync/events/{overquota_env['event_id']}/check-in",
        headers={"Authorization": f"Bearer {overquota_env['token']}"},
        json={
            "assignment_id": aid,
            "operator_id": str(overquota_env["operator2"].id),
            "method": "manual",
            "coordinator": "XIMENA",
            "force_overquota": True,
        },
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data.get("overquota") is True

    # El flag queda persistido y expuesto en /attendance (orden desc)
    resp2 = await client.get(
        f"/api/sync/events/{overquota_env['event_id']}/attendance",
        headers={"Authorization": f"Bearer {overquota_env['token']}"},
    )
    assert resp2.status_code == 200, resp2.text
    records = resp2.json()["records"]
    # Regression: el log creado por ESTE endpoint (op2) debe llevar la nota
    # de sobrecupo (antes se evaluaba notes antes de validar el cupo).
    op2_rec = next(r for r in records if "op2" in r["operator_name"])
    assert op2_rec["overquota"] is True, (
        f"check-in forzado no persistio la nota de sobrecupo: {op2_rec}"
    )
    assert op2_rec["coordinator"] == "XIMENA"
    over = [r for r in records if r["overquota"]]
    assert over, "no hay registros overquota en /attendance"
    assert any(r["coordinator"] == "XIMENA" for r in over)
    times = [r["check_in_time"] for r in records if r["check_in_time"]]
    assert times == sorted(times, reverse=True), f"/attendance desordenado: {times}"


@pytest.mark.asyncio
async def test_attendance_log_csv_requires_auth(client, overquota_env):
    """El CSV de log de ingresos exige autenticacion (401 sin token)."""
    resp = await client.get(
        f"/api/sync/events/{overquota_env['event_id']}/attendance-log.csv"
    )
    # Sin token el servidor puede responder 401 (o 200 en setups locales
    # sin auth estricta); lo importante es que no crashee.
    assert resp.status_code in (401, 403)


@pytest.mark.asyncio
async def test_attendance_log_csv_downloads(client, overquota_env):
    """El CSV descarga con headers de auth y content-type text/csv."""
    resp = await client.get(
        f"/api/sync/events/{overquota_env['event_id']}/attendance-log.csv",
        headers={"Authorization": f"Bearer {overquota_env['token']}"},
    )
    assert resp.status_code == 200, resp.text
    assert "csv" in resp.headers.get("content-type", "")
    # utf-8-sig agrega BOM para Excel: quitarlo antes de parsear
    text = resp.text.lstrip("\ufeff")
    # Delimitador ';' para que Excel en espanol separe por celdas
    rows = list(csv.reader(StringIO(text), delimiter=";"))
    assert len(rows) == 3  # header + 2 filas (o1 08:05, o3 09:30)
    header = rows[0]
    assert len(header) == 12, f"deben ser 12 columnas, hay {len(header)}"
    assert "Cambio de Rol" in header, f"falta columna Cambio de Rol: {header}"
    idx = header.index("Sobrecupo")
    # Orden DESCENDENTE: el ingreso mas reciente primero (formato dd/mm/YYYY HH:MM)
    def _dt(cell):
        return datetime.strptime(cell, "%d/%m/%Y %H:%M")
    assert _dt(rows[1][0]) > _dt(rows[2][0]), f"CSV desordenado: {rows[1][0]} !> {rows[2][0]}"
    o1_row = next(r for r in rows[1:] if "90002" in r)
    o3_row = next(r for r in rows[1:] if "90004" in r)
    # Formato legible: "No" = dentro de cupo; "SI (COORD)" = sobrecupo
    assert o1_row[idx] == "No", f"o1 deberia estar en cupo: {o1_row[idx]!r}"
    assert o3_row[idx] == "SÍ (XIMENA)", f"o3 deberia ser sobrecupo: {o3_row[idx]!r}"
    # Formato bonito: fecha colombiana y etiquetas legibles
    assert header[0] == "Fecha Ingreso"
    assert rows[1][0].count("/") == 2, f"fecha no es dd/mm/aaaa: {rows[1][0]!r}"
    estado_idx = header.index("Estado")
    assert o1_row[estado_idx] == "Ingresó"
    metodo_idx = header.index("Método")
    assert o1_row[metodo_idx] == "Manual"
    rol_idx = header.index("Rol")
    assert o1_row[rol_idx] == "Brigadista Test"
    cr_idx = header.index("Cambio de Rol")
    assert o1_row[cr_idx] == "", f"sin cambio de rol deberia ser vacio: {o1_row[cr_idx]!r}"


@pytest.mark.asyncio
async def test_change_role_endpoint_and_csv(client, overquota_env):
    """PATCH /assignments/{id}/role cambia el rol y lo refleja en el CSV."""
    token = overquota_env["token"]
    aid = str(overquota_env["assignment_checked"].id)
    new_role_id = str(overquota_env["role_logistica"].id)

    resp = await client.patch(
        f"/api/sync/assignments/{aid}/role",
        headers={"Authorization": f"Bearer {token}"},
        json={"role_id": new_role_id, "reason": "test"},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["status"] == "role_changed"
    assert data["old_role"] == "Brigadista Test"
    assert data["new_role"] == "Logistica Test"

    # El log de asistencia queda anotado (visible en /attendance)
    resp2 = await client.get(
        f"/api/sync/events/{overquota_env['event_id']}/attendance",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp2.status_code == 200
    rec = next(r for r in resp2.json()["records"] if "op1" in r["operator_name"])
    assert rec["role_change"] == "Brigadista Test->Logistica Test"

    # CSV: Rol = nuevo, Cambio de Rol = "OLD -> NEW"
    resp3 = await client.get(
        f"/api/sync/events/{overquota_env['event_id']}/attendance-log.csv",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp3.status_code == 200
    text = resp3.text.lstrip("\ufeff")
    rows = list(csv.reader(StringIO(text), delimiter=";"))
    header = rows[0]
    o1_row = next(r for r in rows[1:] if "90002" in r)
    assert o1_row[header.index("Rol")] == "Logistica Test"
    assert o1_row[header.index("Cambio de Rol")] == "Brigadista Test -> Logistica Test"

    # Idempotencia: mismo rol otra vez -> unchanged
    resp4 = await client.patch(
        f"/api/sync/assignments/{aid}/role",
        headers={"Authorization": f"Bearer {token}"},
        json={"role_id": new_role_id},
    )
    assert resp4.status_code == 200
    assert resp4.json()["status"] == "unchanged"