# -*- coding: utf-8 -*-
"""Tests del acceso del rol checkin a la nómina (acceso limitado).

Cubre:
  1. GET /payable con checkin → 200 (puede listar)
  2. POST /sign con checkin → 200 (puede firmar)
  3. POST /records/{id}/pay con checkin → 403 (NO confirma pagos)
  4. GET /invoices/{id} con checkin → 403 (NO genera facturas)
  5. GET /invoices-bulk con checkin → 403
  6. POST /sync con checkin → degrada status "paid" a "signed"
  7. GET /status y /planilla-coordinador con checkin → 200
"""
import uuid
from datetime import datetime, timezone

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.events import Event, EventAssignment
from app.models.operators import Operator
from app.models.payroll import PayrollRecord
from app.models.users import User
from app.services.auth import hash_password


async def _mk_user(db: AsyncSession, doc: str, user_type: str) -> User:
    u = User(
        id=uuid.uuid4(),
        email=f"{doc}@nomina.test",
        password_hash=hash_password("password"),
        first_name="Rol",
        last_name=doc,
        user_type=user_type,
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
        name="Evento Nómina Checkin",
        start_date=datetime(2026, 9, 1, 8, 0, 0, tzinfo=timezone.utc),
        end_date=datetime(2026, 9, 1, 18, 0, 0, tzinfo=timezone.utc),
        location="Plaza",
        status="active",
    )
    db.add(e)
    await db.flush()
    return e


async def _mk_operator_with_assignment(db: AsyncSession, event_id, doc: str):
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
    a = EventAssignment(
        event_id=event_id,
        operator_id=o.id,
        status="checked_in",
    )
    db.add(a)
    await db.flush()
    return a


async def _login(client: AsyncClient, doc: str) -> str:
    resp = await client.post("/api/auth/login", json={
        "document_number": doc, "password": "password",
    })
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


def _h(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
async def nomina_setup(db: AsyncSession):
    """Evento + asignación checked_in + usuarios checkin y admin."""
    event = await _mk_event(db)
    assignment = await _mk_operator_with_assignment(db, event.id, "90001")
    checkin_user = await _mk_user(db, "91000", "checkin")
    admin_user = await _mk_user(db, "91001", "admin")
    await db.commit()
    return event, assignment, checkin_user, admin_user


@pytest.mark.asyncio
async def test_checkin_can_list_payable(client: AsyncClient, nomina_setup):
    event, assignment, checkin_user, _ = nomina_setup
    token = await _login(client, checkin_user.document_number)
    resp = await client.get(f"/api/payroll/events/{event.id}/payable", headers=_h(token))
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["total"] == 1
    assert data["operators"][0]["assignment_id"] == str(assignment.id)


@pytest.mark.asyncio
async def test_checkin_can_sign(client: AsyncClient, nomina_setup):
    event, assignment, checkin_user, _ = nomina_setup
    token = await _login(client, checkin_user.document_number)
    resp = await client.post(
        f"/api/payroll/assignments/{assignment.id}/sign",
        json={"signature_data": "data:image/png;base64,iVBORw0KGgo="},
        headers=_h(token),
    )
    assert resp.status_code == 200, resp.text


@pytest.mark.asyncio
async def test_checkin_cannot_pay(client: AsyncClient, nomina_setup, db: AsyncSession):
    event, assignment, checkin_user, admin_user = nomina_setup
    # crear record firmado por admin para intentar pagarlo con checkin
    admin_token = await _login(client, admin_user.document_number)
    resp = await client.post(
        f"/api/payroll/assignments/{assignment.id}/sign",
        json={"signature_data": "data:image/png;base64,iVBORw0KGgo="},
        headers=_h(admin_token),
    )
    assert resp.status_code == 200, resp.text
    result = await db.execute(
        select(PayrollRecord).where(PayrollRecord.assignment_id == assignment.id)
    )
    record = result.scalar_one()
    assert record.status == "signed"

    checkin_token = await _login(client, checkin_user.document_number)
    resp = await client.post(
        f"/api/payroll/records/{record.id}/pay", headers=_h(checkin_token)
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_checkin_cannot_get_invoice(client: AsyncClient, nomina_setup):
    event, assignment, checkin_user, _ = nomina_setup
    token = await _login(client, checkin_user.document_number)
    resp = await client.get(
        f"/api/payroll/invoices/{uuid.uuid4()}", headers=_h(token)
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_checkin_cannot_bulk_invoices(client: AsyncClient, nomina_setup):
    event, assignment, checkin_user, _ = nomina_setup
    token = await _login(client, checkin_user.document_number)
    resp = await client.get(
        f"/api/payroll/events/{event.id}/invoices-bulk", headers=_h(token)
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_checkin_sync_degrades_paid_to_signed(
    client: AsyncClient, nomina_setup, db: AsyncSession
):
    event, assignment, checkin_user, _ = nomina_setup
    token = await _login(client, checkin_user.document_number)
    resp = await client.post(
        "/api/payroll/sync",
        json={
            "records": [
                {
                    "assignment_id": str(assignment.id),
                    "operator_id": str(assignment.operator_id),
                    "event_id": str(event.id),
                    "signature_data": "data:image/png;base64,iVBORw0KGgo=",
                    "payment_amount": 50000,
                    "role_name": "Operador",
                    "status": "paid",  # checkin intenta pagarlo offline
                    "device_id": "dev-test",
                }
            ]
        },
        headers=_h(token),
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["synced"] == 1

    result = await db.execute(
        select(PayrollRecord).where(PayrollRecord.assignment_id == assignment.id)
    )
    record = result.scalar_one()
    # [ROL CHECKIN] el pago offline se degradó a firma
    assert record.status == "signed"
    assert record.invoice_number is None


@pytest.mark.asyncio
async def test_checkin_can_status_and_planilla(client: AsyncClient, nomina_setup):
    event, assignment, checkin_user, _ = nomina_setup
    token = await _login(client, checkin_user.document_number)
    resp = await client.get(
        f"/api/payroll/events/{event.id}/status", headers=_h(token)
    )
    assert resp.status_code == 200, resp.text

    resp = await client.get(
        f"/api/payroll/events/{event.id}/planilla-coordinador?group_by=none&sort_by=lastname&format=pdf",
        headers=_h(token),
    )
    assert resp.status_code == 200, resp.text