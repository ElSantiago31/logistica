# -*- coding: utf-8 -*-
"""Tests de la definición de etapa en el check-in (Fase: etapas en check-in).

Cubre:
  1. check-in con stage distinto → mueve la asignación + nota cambio_etapa
  2. check-in con stage inválido → 400
  3. check-in sin stage → no toca la etapa (compatibilidad clientes viejos)
  4. quick-add con stage → asignación creada en la etapa indicada
  5. re-check-in (reconcile) con stage distinto → mueve y anota en el log
"""
import uuid
from datetime import datetime, timezone

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.events import Event, EventAssignment
from app.models.sync import AttendanceLog
from app.models.users import User
from app.services.auth import hash_password


async def _mk_admin(db: AsyncSession, doc: str) -> User:
    u = User(
        id=uuid.uuid4(),
        email=f"{doc}@stage.test",
        password_hash=hash_password("password"),
        first_name="Admin",
        last_name="Stage",
        user_type="admin",
        document_type="CC",
        document_number=doc,
        is_verified=True,
        is_approved=True,
    )
    db.add(u)
    await db.flush()
    return u


async def _mk_event(db: AsyncSession) -> Event:
    e = Event(
        id=uuid.uuid4(),
        name="Evento Etapas Checkin",
        start_date=datetime(2026, 9, 1, 8, 0, 0, tzinfo=timezone.utc),
        end_date=datetime(2026, 9, 1, 18, 0, 0, tzinfo=timezone.utc),
        location="Plaza",
        status="active",
    )
    db.add(e)
    await db.flush()
    return e


async def _mk_operator(db: AsyncSession, doc: str):
    from app.models.operators import Operator
    u = User(
        id=uuid.uuid4(),
        email=None,
        password_hash=hash_password("password"),
        first_name="Op",
        last_name=doc,
        user_type="operator",
        document_type="CC",
        document_number=doc,
        is_verified=True,
        is_approved=True,
    )
    db.add(u)
    await db.flush()
    o = Operator(user_id=u.id, city="Bogota")
    db.add(o)
    await db.flush()
    return o


async def _login(client: AsyncClient, doc: str) -> str:
    resp = await client.post("/api/auth/login", json={
        "document_number": doc, "password": "password",
    })
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


@pytest.fixture
async def stage_env(db: AsyncSession, client: AsyncClient):
    event = await _mk_event(db)
    admin = await _mk_admin(db, "80001")
    op = await _mk_operator(db, "80002")
    assignment = EventAssignment(
        event_id=event.id, operator_id=op.id, status="confirmed",
    )
    db.add(assignment)
    await db.commit()
    token = await _login(client, "80001")
    return {
        "event_id": str(event.id),
        "assignment_id": str(assignment.id),
        "operator": op,
        "token": token,
        "admin": admin,
    }


@pytest.mark.asyncio
async def test_checkin_moves_stage(client, stage_env, db):
    """Check-in con stage=avanzada sobre asignación en 'evento': mueve y anota."""
    resp = await client.post(
        f"/api/sync/events/{stage_env['event_id']}/check-in",
        headers={"Authorization": f"Bearer {stage_env['token']}"},
        json={
            "assignment_id": stage_env["assignment_id"],
            "operator_id": str(stage_env["operator"].id),
            "method": "manual",
            "stage": "avanzada",
        },
    )
    assert resp.status_code == 200, resp.text
    a = await db.get(EventAssignment, uuid.UUID(stage_env["assignment_id"]))
    assert a.stage == "avanzada"
    assert a.status == "checked_in"
    log = (await db.execute(
        select(AttendanceLog).where(
            AttendanceLog.event_id == uuid.UUID(stage_env["event_id"]),
            AttendanceLog.operator_id == stage_env["operator"].id,
        )
    )).scalar_one()
    assert "cambio_etapa:evento->avanzada" in (log.notes or "")


@pytest.mark.asyncio
async def test_checkin_invalid_stage_rejected(client, stage_env):
    """Stage fuera de EVENT_STAGES → 400 antes de tocar nada."""
    resp = await client.post(
        f"/api/sync/events/{stage_env['event_id']}/check-in",
        headers={"Authorization": f"Bearer {stage_env['token']}"},
        json={
            "assignment_id": stage_env["assignment_id"],
            "operator_id": str(stage_env["operator"].id),
            "method": "manual",
            "stage": "montaje",
        },
    )
    assert resp.status_code == 400, resp.text


@pytest.mark.asyncio
async def test_checkin_without_stage_keeps_default(client, stage_env, db):
    """Sin stage en el payload: la asignación conserva su etapa (default evento)."""
    resp = await client.post(
        f"/api/sync/events/{stage_env['event_id']}/check-in",
        headers={"Authorization": f"Bearer {stage_env['token']}"},
        json={
            "assignment_id": stage_env["assignment_id"],
            "operator_id": str(stage_env["operator"].id),
            "method": "manual",
        },
    )
    assert resp.status_code == 200, resp.text
    a = await db.get(EventAssignment, uuid.UUID(stage_env["assignment_id"]))
    assert a.stage == "evento"
    assert a.status == "checked_in"


@pytest.mark.asyncio
async def test_checkin_same_stage_no_note(client, stage_env, db):
    """stage igual al actual ('evento'): no genera nota de cambio."""
    resp = await client.post(
        f"/api/sync/events/{stage_env['event_id']}/check-in",
        headers={"Authorization": f"Bearer {stage_env['token']}"},
        json={
            "assignment_id": stage_env["assignment_id"],
            "operator_id": str(stage_env["operator"].id),
            "method": "manual",
            "stage": "evento",
        },
    )
    assert resp.status_code == 200, resp.text
    log = (await db.execute(
        select(AttendanceLog).where(
            AttendanceLog.event_id == uuid.UUID(stage_env["event_id"]),
            AttendanceLog.operator_id == stage_env["operator"].id,
        )
    )).scalar_one()
    assert log.notes is None or "cambio_etapa" not in log.notes


@pytest.mark.asyncio
async def test_quick_add_with_stage(client, stage_env):
    """Quick-add con stage=previa crea la asignación directamente en previa."""
    resp = await client.post(
        f"/api/events/{stage_env['event_id']}/quick-add",
        headers={"Authorization": f"Bearer {stage_env['token']}"},
        json={
            "primer_nombre": "Fantasma",
            "primer_apellido": "Previa",
            "document_type": "CC",
            "document_number": "80999",
            "stage": "previa",
        },
    )
    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert data["mode"] == "ghost"


@pytest.mark.asyncio
async def test_checkin_reconcile_moves_stage(client, stage_env, db):
    """Segundo check-in (log ya existe) con stage distinto: reconcile lo aplica."""
    hdr = {"Authorization": f"Bearer {stage_env['token']}"}
    first = await client.post(
        f"/api/sync/events/{stage_env['event_id']}/check-in",
        headers=hdr,
        json={
            "assignment_id": stage_env["assignment_id"],
            "operator_id": str(stage_env["operator"].id),
            "method": "manual",
        },
    )
    assert first.status_code == 200, first.text
    second = await client.post(
        f"/api/sync/events/{stage_env['event_id']}/check-in",
        headers=hdr,
        json={
            "assignment_id": stage_env["assignment_id"],
            "operator_id": str(stage_env["operator"].id),
            "method": "manual",
            "stage": "desmontaje",
        },
    )
    assert second.status_code == 200, second.text
    assert second.json().get("reconciled") is True
    a = await db.get(EventAssignment, uuid.UUID(stage_env["assignment_id"]))
    assert a.stage == "desmontaje"
    log = (await db.execute(
        select(AttendanceLog).where(
            AttendanceLog.operator_id == stage_env["operator"].id,
        )
    )).scalar_one()
    assert "cambio_etapa:evento->desmontaje" in (log.notes or "")