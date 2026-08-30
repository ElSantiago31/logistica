"""Tests de la importación masiva de operadores desde Excel.

Cubre el flujo de RE-IMPORTACIÓN (actualización de operadores ya asignados
al evento): cambio de cargo, preservación de campos vacíos (COALESCE),
rol no encontrado → NULL y detección de "sin cambios".
"""
import io
import uuid
from datetime import datetime, timezone

import openpyxl
import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.events import Event, EventAssignment
from app.models.users import User
from app.models.roles import Role
from app.services.auth import hash_password

# Encabezados oficiales (orden = EXPECTED_COLUMNS del servicio)
HEADERS = [
    "PRIMER NOMBRE", "SEGUNDO NOMBRE", "PRIMER APELLIDO", "SEGUNDO APELLIDO",
    "TIPO DE DOCUMENTO", "NUMERO CEDULA", "FECHA DE NACIMIENTO", "ROL ASIGANDO",
    "GENERO", "EPS", "PENSION", "DIRECCION DE VIVIENDA", "NUMERO DE CELULAR",
    "NOMBRE CONTACTO EN CASO DE EMERGENCIA",
    "TELEFONO CONTACTO EN CASO DE EMERGENCIA",
    "COORDINADOR QUE LO PROGRAMA",
]

XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _build_xlsx(rows: list[dict]) -> bytes:
    """Genera un .xlsx en memoria con los 16 encabezados oficiales."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(HEADERS)
    for r in rows:
        ws.append([r.get(h, "") for h in HEADERS])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _base_row(**overrides) -> dict:
    row = {
        "PRIMER NOMBRE": "Ana",
        "SEGUNDO NOMBRE": "",
        "PRIMER APELLIDO": "Martinez",
        "SEGUNDO APELLIDO": "",
        "TIPO DE DOCUMENTO": "CC",
        "NUMERO CEDULA": "555001",
        "FECHA DE NACIMIENTO": "",
        "ROL ASIGANDO": "Logistico",
        "GENERO": "F",
        "EPS": "",
        "PENSION": "",
        "DIRECCION DE VIVIENDA": "Calle 12",
        "NUMERO DE CELULAR": "3001112223",
        "NOMBRE CONTACTO EN CASO DE EMERGENCIA": "",
        "TELEFONO CONTACTO EN CASO DE EMERGENCIA": "",
        "COORDINADOR QUE LO PROGRAMA": "",
    }
    row.update(overrides)
    return row


async def _do_import(client: AsyncClient, token: str, event_id, rows: list[dict]):
    data = _build_xlsx(rows)
    return await client.post(
        f"/api/events/{event_id}/import-operators",
        headers={"Authorization": f"Bearer {token}"},
        files={"file": ("operadores.xlsx", data, XLSX_MIME)},
    )


async def _get_assignment(db: AsyncSession, event_id):
    res = await db.execute(
        select(EventAssignment).where(EventAssignment.event_id == event_id)
    )
    return res.scalar_one_or_none()


@pytest.fixture
async def setup_import_env(db: AsyncSession):
    """Evento + roles (Logistico, Universitario) + admin para el token."""
    event = Event(
        id=uuid.uuid4(),
        name="Evento Import Test",
        start_date=datetime(2026, 9, 10, 8, 0, 0, tzinfo=timezone.utc),
        end_date=datetime(2026, 9, 10, 18, 0, 0, tzinfo=timezone.utc),
        location="Bogota",
        status="active",
    )
    role_log = Role(
        id=uuid.uuid4(), name="Logistico", slug="logistico-imp",
        area="Logistica", hierarchy_level=3, is_event_only=False,
    )
    role_univ = Role(
        id=uuid.uuid4(), name="Universitario", slug="universitario-imp",
        area="Logistica", hierarchy_level=3, is_event_only=False,
    )
    admin = User(
        id=uuid.uuid4(), email="admin-import@test.com",
        password_hash=hash_password("password"),
        first_name="Admin", last_name="Import", user_type="admin",
        document_number="99901", is_verified=True, is_approved=True,
    )
    db.add_all([event, role_log, role_univ, admin])
    await db.commit()
    return event, role_log, role_univ, admin


@pytest.fixture
async def admin_token(client: AsyncClient, setup_import_env):
    _, _, _, admin = setup_import_env
    res = await client.post("/api/auth/login", json={
        "document_number": admin.document_number,
        "password": "password",
    })
    assert res.status_code == 200, res.text
    return res.json()["access_token"]


# ── Caso 1: operador nuevo ───────────────────────────────────
async def test_import_creates_new_operator(client, db, admin_token, setup_import_env):
    event, role_log, _, _ = setup_import_env
    res = await _do_import(client, admin_token, event.id, [_base_row()])
    assert res.status_code == 200, res.text
    summary = res.json()
    assert summary["created"] == 1
    assert summary["updated"] == 0
    assert summary["rows"][0]["status"] == "created"

    await db.rollback()
    assign = await _get_assignment(db, event.id)
    assert assign is not None
    assert str(assign.role_id) == str(role_log.id)
    assert assign.status == "confirmed"

    user = (await db.execute(
        select(User).where(User.document_number == "555001")
    )).scalar_one()
    assert user.email == "555001@operador.temp"


# ── Caso 2: re-import cambia el cargo SOLO del evento ────────
async def test_reimport_updates_role_same_event(client, db, admin_token, setup_import_env):
    event, role_log, role_univ, _ = setup_import_env
    r1 = await _do_import(client, admin_token, event.id, [_base_row()])
    assert r1.status_code == 200, r1.text

    r2 = await _do_import(client, admin_token, event.id, [
        _base_row(**{"ROL ASIGANDO": "Universitario"})
    ])
    assert r2.status_code == 200, r2.text
    summary = r2.json()
    assert summary["updated"] == 1
    assert summary["already_assigned"] == 0
    assert summary["rows"][0]["status"] == "updated"
    assert "cargo" in summary["rows"][0]["message"]

    await db.rollback()
    assign = await _get_assignment(db, event.id)
    assert str(assign.role_id) == str(role_univ.id)   # cargo del evento cambió
    user = (await db.execute(
        select(User).where(User.document_number == "555001")
    )).scalar_one()
    assert str(user.role_id) == str(role_log.id)      # rol global intacto


# ── Caso 3: campos vacíos NO borran valores existentes ───────
async def test_reimport_empty_fields_preserve_existing(client, db, admin_token, setup_import_env):
    event, _, _, _ = setup_import_env
    await _do_import(client, admin_token, event.id, [_base_row()])

    r2 = await _do_import(client, admin_token, event.id, [
        _base_row(**{
            "NUMERO DE CELULAR": "",
            "DIRECCION DE VIVIENDA": "",
        })
    ])
    assert r2.status_code == 200, r2.text
    summary = r2.json()
    # Nada cambió de verdad (vacíos ignorados, resto idéntico)
    assert summary["updated"] == 0
    assert summary["already_assigned"] == 1

    await db.rollback()
    user = (await db.execute(
        select(User).where(User.document_number == "555001")
    )).scalar_one()
    assert user.phone == "3001112223"                 # teléfono conservado
    assign = await _get_assignment(db, event.id)
    from app.models.operators import Operator
    op = (await db.execute(
        select(Operator).where(Operator.id == assign.operator_id)
    )).scalar_one()
    assert op.address == "Calle 12"                   # dirección conservada


# ── Caso 4: rol inexistente → asignación sin cargo ───────────
async def test_reimport_role_not_found_nulls_role(client, db, admin_token, setup_import_env):
    event, role_log, _, _ = setup_import_env
    await _do_import(client, admin_token, event.id, [_base_row()])

    r2 = await _do_import(client, admin_token, event.id, [
        _base_row(**{"ROL ASIGANDO": "Carguero Nasa 3000"})
    ])
    assert r2.status_code == 200, r2.text
    summary = r2.json()
    assert summary["updated"] == 1
    row = summary["rows"][0]
    assert row["status"] == "updated"
    assert any("Rol" in w for w in row["warnings"])

    await db.rollback()
    assign = await _get_assignment(db, event.id)
    assert assign.role_id is None                     # quedó sin cargo


# ── Caso 5: celda de rol vacía conserva el cargo actual ──────
async def test_reimport_empty_role_keeps_current(client, db, admin_token, setup_import_env):
    event, role_log, _, _ = setup_import_env
    await _do_import(client, admin_token, event.id, [_base_row()])

    r2 = await _do_import(client, admin_token, event.id, [
        _base_row(**{"ROL ASIGANDO": ""})
    ])
    assert r2.status_code == 200, r2.text
    summary = r2.json()
    assert summary["rows"][0]["status"] == "already_assigned"

    await db.rollback()
    assign = await _get_assignment(db, event.id)
    assert str(assign.role_id) == str(role_log.id)    # cargo conservado


# ── Caso 6: fila idéntica → sin cambios ──────────────────────
async def test_reimport_identical_row_no_changes(client, admin_token, setup_import_env):
    event, _, _, _ = setup_import_env
    await _do_import(client, admin_token, event.id, [_base_row()])

    r2 = await _do_import(client, admin_token, event.id, [_base_row()])
    assert r2.status_code == 200, r2.text
    summary = r2.json()
    assert summary["updated"] == 0
    assert summary["already_assigned"] == 1
    assert summary["rows"][0]["status"] == "already_assigned"