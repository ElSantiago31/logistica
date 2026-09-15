"""Tests de la importación masiva de operadores desde Excel.

Cubre el flujo de RE-IMPORTACIÓN (actualización de operadores ya asignados
al evento): cambio de cargo, preservación de campos vacíos (COALESCE),
rol no encontrado → NULL y detección de "sin cambios".
"""
import asyncio
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
    "ETAPA",
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
        "ETAPA": "",
    }
    row.update(overrides)
    return row


class _ImportResponse:
    """Wrapper compatible con httpx.Response para el flujo asíncrono.

    El POST de importación ahora responde 202 + job_id (job en background).
    Este helper hace polling del endpoint de status hasta que el job
    termina y expone ``.status_code``/``.json()`` con el ImportSummary,
    manteniendo compatibles los asserts de los tests existentes:
      - completed → 200 + summary
      - failed    → 500 + {"detail": error}
    """

    def __init__(self, status_code: int, payload: dict):
        self.status_code = status_code
        self._payload = payload

    def json(self) -> dict:
        return self._payload


async def _do_import(client: AsyncClient, token: str, event_id, rows: list[dict]):
    data = _build_xlsx(rows)
    res = await client.post(
        f"/api/events/{event_id}/import-operators",
        headers={"Authorization": f"Bearer {token}"},
        files={"file": ("operadores.xlsx", data, XLSX_MIME)},
    )
    if res.status_code != 202:
        return res  # error de validación (400/403/404) tal cual

    job_id = res.json()["job_id"]
    headers = {"Authorization": f"Bearer {token}"}
    for _ in range(120):  # ~60s máximo esperando el job
        await asyncio.sleep(0.5)  # cede el loop: el job avanza en background
        st = await client.get(f"/api/events/import/status/{job_id}", headers=headers)
        if st.status_code != 200:
            return _ImportResponse(st.status_code, {"detail": st.json().get("detail")})
        body = st.json()
        if body["status"] == "completed":
            return _ImportResponse(200, body["summary"])
        if body["status"] == "failed":
            return _ImportResponse(500, {"detail": body.get("error")})
    return _ImportResponse(504, {"detail": "timeout esperando el job de importación"})


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


# ── Caso 7: roles avanzados event-only vía importación ───────
async def test_import_advanced_roles_no_collision(client, db, admin_token, setup_import_env):
    """'Operador Logístico Avanzada' y 'Brigadista Avanzada' deben matchear
    su propio rol (event-only) y NO colisionar con los roles básicos."""
    event, role_log, _, _ = setup_import_env
    role_adv_log = Role(
        id=uuid.uuid4(), name="Operador Logístico Avanzada",
        slug="operador_logistico_avanzado",
        area="Logistica", hierarchy_level=3, is_event_only=True,
    )
    role_adv_brig = Role(
        id=uuid.uuid4(), name="Brigadista Avanzada",
        slug="brigadista_avanzado",
        area="Emergencias", hierarchy_level=3, is_event_only=True,
    )
    db.add_all([role_adv_log, role_adv_brig])
    await db.commit()

    res = await _do_import(client, admin_token, event.id, [
        _base_row(**{"NUMERO CEDULA": "555100", "ROL ASIGANDO": "Operador Logístico Avanzada"}),
        _base_row(**{"NUMERO CEDULA": "555101", "ROL ASIGANDO": "Operador Logistico"}),
        _base_row(**{"NUMERO CEDULA": "555102", "ROL ASIGANDO": "Brigadista Avanzada"}),
    ])
    assert res.status_code == 200, res.text
    summary = res.json()
    assert summary["created"] == 3
    for row in summary["rows"]:
        assert not any("no encontrado" in w for w in (row.get("warnings") or [])), row

    await db.rollback()
    res2 = await db.execute(
        select(EventAssignment).where(EventAssignment.event_id == event.id)
    )
    role_ids = {str(a.role_id) for a in res2.scalars().all()}
    assert str(role_adv_log.id) in role_ids      # avanzada NO cayó en la básica
    assert str(role_adv_brig.id) in role_ids     # brigadista avanzada matcheó
    assert str(role_log.id) in role_ids          # rol básico sigue matcheando


# ── Caso 8: catálogo excluye roles event-only por defecto ────
async def test_catalog_roles_excludes_advanced_event_only(client, db, setup_import_env):
    """/api/catalogs/roles no debe listar los roles event-only (registro de
    operadores), pero sí listarlos con include_event_only=true (eventos)."""
    role_adv = Role(
        id=uuid.uuid4(), name="Operador Logístico Avanzada",
        slug="catalogo-avanzado-test",
        area="Logistica", hierarchy_level=3, is_event_only=True,
    )
    db.add(role_adv)
    await db.commit()

    r1 = await client.get("/api/catalogs/roles")
    assert r1.status_code == 200, r1.text
    slugs = [r["slug"] for r in r1.json()]
    assert "catalogo-avanzado-test" not in slugs

    r2 = await client.get("/api/catalogs/roles?include_event_only=true")
    assert r2.status_code == 200, r2.text
    slugs2 = [r["slug"] for r in r2.json()]
    assert "catalogo-avanzado-test" in slugs2


# ── Flujo asíncrono: 202 + job_id + endpoint de status ───────
async def test_import_returns_202_with_job(client, admin_token, setup_import_env):
    """El POST debe responder 202 inmediato con job_id + status_url."""
    event, _, _, _ = setup_import_env
    data = _build_xlsx([_base_row()])
    res = await client.post(
        f"/api/events/{event.id}/import-operators",
        headers={"Authorization": f"Bearer {admin_token}"},
        files={"file": ("operadores.xlsx", data, XLSX_MIME)},
    )
    assert res.status_code == 202, res.text
    body = res.json()
    assert body["job_id"]
    assert body["status"] == "queued"
    assert body["status_url"] == f"/api/events/import/status/{body['job_id']}"


async def test_import_status_unknown_job_404(client, admin_token):
    """Status de un job inexistente → 404."""
    res = await client.get(
        "/api/events/import/status/00000000-0000-0000-0000-000000000000",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert res.status_code == 404


async def test_import_status_requires_admin(client, db, setup_import_env):
    """Un operador NO puede consultar el estado de un job (403)."""
    op_user = User(
        id=uuid.uuid4(), email="op-status@test.com",
        password_hash=hash_password("password"),
        first_name="Op", last_name="Status", user_type="operator",
        document_number="555900", is_verified=True, is_approved=True,
    )
    db.add(op_user)
    await db.commit()

    res = await client.post("/api/auth/login", json={
        "document_number": "555900", "password": "password",
    })
    assert res.status_code == 200, res.text
    op_token = res.json()["access_token"]

    res2 = await client.get(
        "/api/events/import/status/cualquier-job-id",
        headers={"Authorization": f"Bearer {op_token}"},
    )
    assert res2.status_code == 403


async def test_import_job_completes_and_persists(client, db, admin_token, setup_import_env):
    """El job en background procesa el Excel y el status incluye el summary."""
    event, _, _, _ = setup_import_env
    data = _build_xlsx([_base_row()])
    res = await client.post(
        f"/api/events/{event.id}/import-operators",
        headers={"Authorization": f"Bearer {admin_token}"},
        files={"file": ("operadores.xlsx", data, XLSX_MIME)},
    )
    assert res.status_code == 202, res.text
    job_id = res.json()["job_id"]

    headers = {"Authorization": f"Bearer {admin_token}"}
    final = None
    for _ in range(120):  # ~60s
        await asyncio.sleep(0.5)
        st = await client.get(f"/api/events/import/status/{job_id}", headers=headers)
        assert st.status_code == 200, st.text
        body = st.json()
        if body["status"] in ("completed", "failed"):
            final = body
            break
    assert final is not None, "el job no terminó en 60s"
    assert final["status"] == "completed", final.get("error")
    assert final["summary"]["created"] == 1

    # El operador quedó persistido en la BD
    await db.rollback()
    user = (await db.execute(
        select(User).where(User.document_number == "555001")
    )).scalar_one()
    assert user is not None


# ──── ETAPA (stages): columna ETAPA del Excel ─────────────────────────────

async def test_import_stage_creates_assignment_in_stage(client, db, admin_token, setup_import_env):
    """Fila con ETAPA='previa' crea la asignación con stage='previa'."""
    event, _, _, _ = setup_import_env
    res = await _do_import(client, admin_token, event.id, [
        _base_row(**{"ETAPA": "previa"}),
    ])
    assert res.status_code == 200, res.text
    assert res.json()["created"] == 1

    await db.rollback()
    assign = await _get_assignment(db, event.id)
    assert assign is not None
    assert assign.stage == "previa"


async def test_import_stage_default_is_evento(client, db, admin_token, setup_import_env):
    """Sin columna ETAPA (legacy) la asignación cae en 'evento'."""
    event, _, _, _ = setup_import_env
    res = await _do_import(client, admin_token, event.id, [_base_row()])
    assert res.status_code == 200, res.text

    await db.rollback()
    assign = await _get_assignment(db, event.id)
    assert assign is not None
    assert assign.stage == "evento"


async def test_import_same_operator_two_stages(client, db, admin_token, setup_import_env):
    """Mismo documento en dos etapas = dos asignaciones (doble turno), sin error."""
    event, _, _, _ = setup_import_env
    res = await _do_import(client, admin_token, event.id, [
        _base_row(**{"ETAPA": "previa"}),
        _base_row(**{"ETAPA": "desmontaje"}),
    ])
    assert res.status_code == 200, res.text
    summary = res.json()
    # La 1ª fila crea el operador; la 2ª (misma persona, otra etapa) lo
    # asigna como existente. Nunca debe ser error ni duplicado.
    assert summary["created"] + summary["existing"] == 2
    assert summary["errors"] == 0

    await db.rollback()
    result = await db.execute(
        select(EventAssignment).where(EventAssignment.event_id == event.id)
    )
    assigns = result.scalars().all()
    assert len(assigns) == 2
    assert {a.stage for a in assigns} == {"previa", "desmontaje"}


async def test_import_duplicate_same_stage_is_error(client, db, admin_token, setup_import_env):
    """Mismo documento dos veces EN LA MISMA etapa → error de duplicado."""
    event, _, _, _ = setup_import_env
    res = await _do_import(client, admin_token, event.id, [
        _base_row(**{"ETAPA": "previa"}),
        _base_row(**{"ETAPA": "previa", "PRIMER NOMBRE": "Ana2"}),
    ])
    assert res.status_code == 200, res.text
    summary = res.json()
    assert summary["created"] == 1
    assert summary["errors"] == 1
    assert "duplicado" in summary["rows"][1]["message"].lower()


async def test_import_invalid_stage_warns_and_defaults(client, db, admin_token, setup_import_env):
    """ETAPA con valor inválido → warning por fila + asignación en 'evento'."""
    event, _, _, _ = setup_import_env
    res = await _do_import(client, admin_token, event.id, [
        _base_row(**{"ETAPA": "montaje"}),
    ])
    assert res.status_code == 200, res.text
    row0 = res.json()["rows"][0]
    assert row0["status"] == "created"
    assert any("no válida" in w for w in row0.get("warnings", []))

    await db.rollback()
    assign = await _get_assignment(db, event.id)
    assert assign.stage == "evento"


async def test_reimport_stage_updates_only_that_stage(client, db, admin_token, setup_import_env):
    """Re-importar la fila de una etapa NO toca la asignación de la otra etapa."""
    event, role_log, role_univ, _ = setup_import_env
    res = await _do_import(client, admin_token, event.id, [
        _base_row(**{"ETAPA": "previa"}),
        _base_row(**{"ETAPA": "evento"}),
    ])
    assert res.status_code == 200, res.text

    # Re-import: solo la fila de 'previa' cambia de rol
    res2 = await _do_import(client, admin_token, event.id, [
        _base_row(**{"ETAPA": "previa", "ROL ASIGANDO": "Universitario"}),
    ])
    assert res2.status_code == 200, res2.text
    summary = res2.json()
    assert summary["updated"] == 1, summary["rows"]

    await db.rollback()
    result = await db.execute(
        select(EventAssignment).where(EventAssignment.event_id == event.id)
    )
    assigns = {a.stage: a for a in result.scalars().all()}
    assert str(assigns["previa"].role_id) == str(role_univ.id)
    assert str(assigns["evento"].role_id) == str(role_log.id)
