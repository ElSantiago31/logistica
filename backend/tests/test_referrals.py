# -*- coding: utf-8 -*-
"""Tests para el modulo de Referidos (F9 del plan).

Cubre:
- Generacion y formato de codigos (AC-NOMBRE-XXXX).
- Validacion: valido, normalizacion, inactivo, inexistente.
- Creacion de codigo: happy path, duplicado, operador inexistente.
- Toggle de codigo (habilitar/deshabilitar).
- Registro de referido: happy path, duplicado, autoreferido.
- Metricas derivadas: cupos = referidos que TRABAJARON (checked_in).
- Auditoria: code_created queda en referral_audit_logs.
- API SuperAdmin: stats, list, create, toggle, export, detail.
- Registro publico: codigo invalido -> 400 fail-fast (no crea nada).
"""
import uuid
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from sqlalchemy import select

from app.main import app
from app.dependencies.auth import require_superadmin
from app.models.users import User
from app.models.operators import Operator
from app.models.events import Event, EventAssignment
from app.models.referrals import ReferralAuditLog, ReferralCode
from app.services.referrals import (
    ReferralError,
    create_code_for_operator,
    generate_code_from_name,
    get_referrer_metrics,
    register_referral,
    set_code_active,
    validate_code,
)

_DUMMY_DOC = "data:image/jpeg;base64," + "A" * 200


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
async def _mk_user(db, *, user_type="operator", first="Juan", last="Perez"):
    u = User(
        email=f"{uuid.uuid4().hex[:10]}@test.com",
        password_hash="x",
        first_name=first,
        last_name=last,
        document_number=f"79{uuid.uuid4().int % 10**8:08d}",
        user_type=user_type,
        is_verified=True,
    )
    db.add(u)
    await db.flush()
    return u


async def _mk_operator(db, *, first="Juan", last="Perez"):
    u = await _mk_user(db, first=first, last=last)
    o = Operator(user_id=u.id)
    db.add(o)
    await db.flush()
    return o


async def _mk_event(db, *, n=0):
    e = Event(
        name=f"Evento Test {n}",
        location="Bogota",
        start_date=datetime(2026, 1, 10, 8, 0, tzinfo=timezone.utc),
        end_date=datetime(2026, 1, 10, 18, 0, tzinfo=timezone.utc),
    )
    db.add(e)
    await db.flush()
    return e


def _mk_assignment(db, event_id, operator_id, status="confirmed"):
    a = EventAssignment(event_id=event_id, operator_id=operator_id, status=status)
    db.add(a)
    return a


# ---------------------------------------------------------------------------
# Servicio: generacion de codigo
# ---------------------------------------------------------------------------
class TestGenerateCode:
    def test_formato_ac_nombre_sufijo(self):
        code = generate_code_from_name("Maria Jose")
        assert code.startswith("AC-")
        parts = code.split("-")
        assert len(parts) == 3, "formato AC-NOMBRE-XXXX"
        assert parts[1] == "MARIA", "primera palabra del nombre, sin tildes"
        assert len(parts[2]) == 4, "sufijo de 4 caracteres"
        assert parts[2].isalnum()

    def test_sufijo_aleatorio_entre_llamadas(self):
        codes = {generate_code_from_name("Santiago") for _ in range(10)}
        assert len(codes) > 1, "el sufijo debe variar entre llamadas"


# ---------------------------------------------------------------------------
# Servicio: validacion de codigo
# ---------------------------------------------------------------------------
class TestValidateCode:
    async def test_codigo_valido(self, db):
        ref = await _mk_operator(db)
        rc = ReferralCode(operator_id=ref.id, code="AC-VALID-0001")
        db.add(rc)
        await db.flush()
        found = await validate_code(db, "AC-VALID-0001")
        assert found.id == rc.id

    async def test_normaliza_mayusculas_y_espacios(self, db):
        ref = await _mk_operator(db)
        db.add(ReferralCode(operator_id=ref.id, code="AC-MINUS-A2B3"))
        await db.flush()
        found = await validate_code(db, "  ac-minus-a2b3  ")
        assert found.code == "AC-MINUS-A2B3"

    async def test_codigo_inactivo_rechazado(self, db):
        ref = await _mk_operator(db)
        db.add(ReferralCode(operator_id=ref.id, code="AC-INACT-0002", is_active=False))
        await db.flush()
        with pytest.raises(ReferralError) as ei:
            await validate_code(db, "AC-INACT-0002")
        assert ei.value.status_code == 410

    async def test_codigo_inexistente_rechazado(self, db):
        with pytest.raises(ReferralError) as ei:
            await validate_code(db, "AC-GHOST-9999")
        assert ei.value.status_code == 404


# ---------------------------------------------------------------------------
# Servicio: crear / toggle codigo
# ---------------------------------------------------------------------------
class TestCreateAndToggleCode:
    async def test_crear_codigo_happy_path(self, db):
        sa = await _mk_user(db, user_type="superadmin", first="Super", last="Admin")
        ref = await _mk_operator(db, first="Santiago", last="Gomez")
        code = await create_code_for_operator(db, ref.id, sa.id)
        assert code.code.startswith("AC-SANTIAGO-")
        assert code.is_active is True
        assert code.operator_id == ref.id

    async def test_crear_codigo_duplicado_rechazado(self, db):
        sa = await _mk_user(db, user_type="superadmin")
        ref = await _mk_operator(db)
        await create_code_for_operator(db, ref.id, sa.id)
        with pytest.raises(ReferralError) as ei:
            await create_code_for_operator(db, ref.id, sa.id)
        assert ei.value.status_code == 409

    async def test_crear_codigo_operador_inexistente(self, db):
        sa = await _mk_user(db, user_type="superadmin")
        with pytest.raises(ReferralError) as ei:
            await create_code_for_operator(db, uuid.uuid4(), sa.id)
        assert ei.value.status_code == 404

    async def test_toggle_desactiva_y_activa(self, db):
        sa = await _mk_user(db, user_type="superadmin")
        ref = await _mk_operator(db)
        rc = ReferralCode(operator_id=ref.id, code="AC-TOGGL-0003")
        db.add(rc)
        await db.flush()
        off = await set_code_active(db, rc.id, False, sa.id)
        assert off.is_active is False
        on = await set_code_active(db, rc.id, True, sa.id)
        assert on.is_active is True


# ---------------------------------------------------------------------------
# Servicio: registro de referido
# ---------------------------------------------------------------------------
class TestRegisterReferral:
    async def test_registro_happy_path(self, db):
        referrer = await _mk_operator(db)
        referred = await _mk_operator(db)
        db.add(ReferralCode(operator_id=referrer.id, code="AC-HAPPY-0004"))
        await db.flush()
        r = await register_referral(db, code="AC-HAPPY-0004", referred_operator_id=referred.id)
        assert r.referrer_operator_id == referrer.id
        assert r.referred_operator_id == referred.id
        assert r.code_used == "AC-HAPPY-0004"
        assert r.registered_at is not None

    async def test_registro_duplicado_rechazado(self, db):
        referrer = await _mk_operator(db)
        referred = await _mk_operator(db)
        db.add(ReferralCode(operator_id=referrer.id, code="AC-DUPLI-0005"))
        await db.flush()
        await register_referral(db, code="AC-DUPLI-0005", referred_operator_id=referred.id)
        with pytest.raises(ReferralError) as ei:
            await register_referral(db, code="AC-DUPLI-0005", referred_operator_id=referred.id)
        assert ei.value.status_code == 409

    async def test_autoreferido_rechazado(self, db):
        referrer = await _mk_operator(db)
        db.add(ReferralCode(operator_id=referrer.id, code="AC-SELF0-0006"))
        await db.flush()
        with pytest.raises(ReferralError) as ei:
            await register_referral(db, code="AC-SELF0-0006", referred_operator_id=referrer.id)
        assert ei.value.status_code == 400


# ---------------------------------------------------------------------------
# Servicio: metricas derivadas (cupos)
# ---------------------------------------------------------------------------
class TestDerivedMetrics:
    async def test_cupos_solo_por_quienes_trabajaron(self, db):
        referrer = await _mk_operator(db)
        db.add(ReferralCode(operator_id=referrer.id, code="AC-METRI-0007"))
        await db.flush()
        r1 = await _mk_operator(db)  # trabajo (checked_in)
        r2 = await _mk_operator(db)  # solo asignado (confirmed)
        r3 = await _mk_operator(db)  # sin asignaciones
        for r in (r1, r2, r3):
            await register_referral(db, code="AC-METRI-0007", referred_operator_id=r.id)

        ev = await _mk_event(db)
        _mk_assignment(db, ev.id, r1.id, status="checked_in")
        _mk_assignment(db, ev.id, r2.id, status="confirmed")
        await db.flush()

        m = await get_referrer_metrics(db, referrer.id)
        assert m["total_referrals"] == 3
        assert m["active_referrals"] == 3
        assert m["assigned_referrals"] == 2
        assert m["worked_referrals"] == 1

    async def test_varios_eventos_no_duplican_cupo(self, db):
        referrer = await _mk_operator(db)
        db.add(ReferralCode(operator_id=referrer.id, code="AC-METRI-0008"))
        await db.flush()
        r1 = await _mk_operator(db)
        await register_referral(db, code="AC-METRI-0008", referred_operator_id=r1.id)
        ev1 = await _mk_event(db, n=1)
        ev2 = await _mk_event(db, n=2)
        _mk_assignment(db, ev1.id, r1.id, status="checked_in")
        _mk_assignment(db, ev2.id, r1.id, status="checked_in")
        await db.flush()

        m = await get_referrer_metrics(db, referrer.id)
        assert m["worked_referrals"] == 1


# ---------------------------------------------------------------------------
# Auditoria
# ---------------------------------------------------------------------------
class TestAuditLog:
    async def test_creacion_de_codigo_deja_audit(self, db):
        sa = await _mk_user(db, user_type="superadmin")
        ref = await _mk_operator(db)
        await create_code_for_operator(db, ref.id, sa.id)  # hace commit
        logs = (await db.scalars(
            select(ReferralAuditLog).where(
                ReferralAuditLog.action == "code_created",
                ReferralAuditLog.referrer_operator_id == ref.id,
            )
        )).all()
        assert len(logs) == 1


# ---------------------------------------------------------------------------
# API SuperAdmin
# ---------------------------------------------------------------------------
@pytest.fixture
async def sa_client(db, client):
    # El id del superadmin debe existir en users: la auditoria
    # (referral_audit_logs.user_id) tiene FK a users.id.
    sa = User(
        email=f"sa-{uuid.uuid4().hex[:8]}@test.com",
        password_hash="x",
        first_name="Super", last_name="Admin",
        user_type="superadmin", is_verified=True,
    )
    db.add(sa)
    await db.commit()
    fake = SimpleNamespace(
        id=sa.id, email=sa.email,
        first_name="Super", last_name="Admin", user_type="superadmin",
    )
    app.dependency_overrides[require_superadmin] = lambda: fake
    yield client
    app.dependency_overrides.pop(require_superadmin, None)


class TestReferralsAPI:
    async def test_stats_vacio(self, sa_client):
        r = await sa_client.get("/api/referrals/stats")
        assert r.status_code == 200
        body = r.json()
        assert body["total_codes"] == 0
        assert body["active_codes"] == 0

    async def test_stats_con_datos(self, db, sa_client):
        ref = await _mk_operator(db)
        db.add(ReferralCode(operator_id=ref.id, code="AC-STATS-0009"))
        await db.commit()
        r = await sa_client.get("/api/referrals/stats")
        assert r.status_code == 200
        body = r.json()
        assert body["total_codes"] == 1
        assert body["active_codes"] == 1

    async def test_list_codes(self, db, sa_client):
        ref = await _mk_operator(db, first="Santiago", last="Perez")
        db.add(ReferralCode(operator_id=ref.id, code="AC-LISTC-0010"))
        await db.commit()
        r = await sa_client.get("/api/referrals/codes")
        assert r.status_code == 200
        items = r.json()
        item = next(c for c in items if c["code"] == "AC-LISTC-0010")
        assert item["operator_name"] == "Santiago Perez"
        assert item["total_referrals"] == 0

    async def test_create_code_endpoint(self, db, sa_client):
        ref = await _mk_operator(db, first="Pepito", last="Lopez")
        await db.commit()
        r = await sa_client.post("/api/referrals/codes", json={"operator_id": str(ref.id)})
        assert r.status_code == 201, r.text
        body = r.json()
        assert body["code"].startswith("AC-PEPITO-")
        assert body["is_active"] is True

    async def test_create_code_duplicado_409(self, db, sa_client):
        ref = await _mk_operator(db)
        await db.commit()
        r1 = await sa_client.post("/api/referrals/codes", json={"operator_id": str(ref.id)})
        assert r1.status_code == 201
        r2 = await sa_client.post("/api/referrals/codes", json={"operator_id": str(ref.id)})
        assert r2.status_code == 409

    async def test_toggle_code_endpoint(self, db, sa_client):
        ref = await _mk_operator(db)
        db.add(ReferralCode(operator_id=ref.id, code="AC-TOGG2-0011"))
        await db.commit()
        codes = (await sa_client.get("/api/referrals/codes")).json()
        cid = next(c["id"] for c in codes if c["code"] == "AC-TOGG2-0011")
        r = await sa_client.patch(f"/api/referrals/codes/{cid}", json={"is_active": False})
        assert r.status_code == 200
        assert r.json()["is_active"] is False

    async def test_export_xlsx(self, sa_client):
        r = await sa_client.get("/api/referrals/export")
        assert r.status_code == 200
        assert r.content[:2] == b"PK", "firma ZIP de un .xlsx"

    async def test_referrer_detail(self, db, sa_client):
        referrer = await _mk_operator(db, first="Ana", last="Restrepo")
        referred = await _mk_operator(db, first="Luis", last="Diaz")
        db.add(ReferralCode(operator_id=referrer.id, code="AC-DETAL-0012"))
        await db.flush()
        await register_referral(db, code="AC-DETAL-0012", referred_operator_id=referred.id)

        r = await sa_client.get(f"/api/referrals/{referrer.id}")
        assert r.status_code == 200
        body = r.json()
        assert body["operator_name"] == "Ana Restrepo"
        assert body["metrics"]["total_referrals"] == 1
        assert len(body["referrals"]) == 1
        assert body["referrals"][0]["name"] == "Luis Diaz"

    async def test_register_publico_codigo_invalido_400(self, db, sa_client):
        payload = {
            "email": f"{uuid.uuid4().hex[:8]}@test.com",
            "password": "Secreta123",
            "first_name": "Pepito",
            "last_name": "Perez",
            "phone": "3001112233",
            "document_number": f"80{uuid.uuid4().int % 10**8:08d}",
            "photo_data": _DUMMY_DOC,
            "rut_data": _DUMMY_DOC,
            "id_document_front_data": _DUMMY_DOC,
            "id_document_back_data": _DUMMY_DOC,
            "referral_code": "AC-INVA-0000",
        }
        r = await sa_client.post("/api/auth/register", json=payload)
        assert r.status_code == 400, "codigo invalido debe rechazar fail-fast"
        assert "referido" in r.json()["detail"].lower()
        # Fail-fast: no se creo ningun usuario con ese email
        users = (await db.scalars(select(User).where(User.email == payload["email"]))).all()
        assert users == []
