# -*- coding: utf-8 -*-
"""Tests de validación de role_id en creación/edición de eventos.

Regresión del 500 en POST /api/events/: el frontend puede enviar
role_ids cacheados (de otra BD / service worker) que no existen en la
tabla roles, produciendo ForeignKeyViolationError (500 crudo).

Ahora el servicio valida ANTES del INSERT y responde 400 con mensaje
accionable, sin crear el evento a medias ni borrar needs existentes.
"""
import uuid
from datetime import datetime, timezone

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from app.models.events import Event, EventStaffNeed
from app.models.roles import Role
from app.models.users import User
from app.schemas.events import EventCreate, EventUpdate, StaffNeedCreate
from app.services import events as svc


async def _mk_admin(db):
    u = User(
        email=f"admin-{uuid.uuid4().hex[:10]}@test.com",
        password_hash="x",
        first_name="Admin",
        last_name="Test",
        user_type="admin",
        is_verified=True,
    )
    db.add(u)
    await db.flush()
    return u


async def _mk_role(db):
    suffix = uuid.uuid4().hex[:6]
    r = Role(name=f"Rol Valido {suffix}", slug=f"rv-{suffix}")
    db.add(r)
    await db.flush()
    return r


def _payload(role_id):
    return EventCreate(
        name=f"Evento Fix {uuid.uuid4().hex[:6]}",
        location="Bogota",
        start_date=datetime(2026, 11, 10, 8, 0, tzinfo=timezone.utc),
        end_date=datetime(2026, 11, 12, 18, 0, tzinfo=timezone.utc),
        staff_needs=[
            StaffNeedCreate(role_id=role_id, quantity_needed=4, stage="evento"),
        ],
    )


async def test_create_event_with_invalid_role_id_returns_400(db):
    """Rol inexistente -> HTTPException 400, y NO se crea el evento."""
    admin = await _mk_admin(db)
    fake_role = uuid.uuid4()  # no existe en roles

    with pytest.raises(HTTPException) as exc:
        await svc.create_event(db, _payload(fake_role), admin.id)
    assert exc.value.status_code == 400
    assert "Roles inválidos" in exc.value.detail

    # Nada quedó persistido a medias.
    result = await db.execute(select(Event).where(Event.created_by == admin.id))
    assert result.scalars().first() is None


async def test_create_event_with_valid_role_id_works(db):
    """Rol real -> el evento se crea con sus needs normalmente."""
    admin = await _mk_admin(db)
    role = await _mk_role(db)

    event = await svc.create_event(db, _payload(role.id), admin.id)
    assert event.id is not None

    result = await db.execute(
        select(EventStaffNeed).where(EventStaffNeed.event_id == event.id)
    )
    needs = result.scalars().all()
    assert len(needs) == 1
    assert needs[0].role_id == role.id
    assert needs[0].quantity_needed == 4


async def test_update_event_with_invalid_role_keeps_old_needs(db):
    """Update con rol inexistente -> 400 y el evento CONSERVA sus needs."""
    admin = await _mk_admin(db)
    role = await _mk_role(db)
    event = await svc.create_event(db, _payload(role.id), admin.id)

    bad_update = EventUpdate(
        staff_needs=[
            {"role_id": str(uuid.uuid4()), "quantity_needed": 9, "stage": "evento"},
        ]
    )
    with pytest.raises(HTTPException) as exc:
        await svc.update_event(db, event.id, bad_update, admin.id)
    assert exc.value.status_code == 400

    # Los needs originales siguen intactos.
    result = await db.execute(
        select(EventStaffNeed).where(EventStaffNeed.event_id == event.id)
    )
    needs = result.scalars().all()
    assert len(needs) == 1
    assert needs[0].role_id == role.id
    assert needs[0].quantity_needed == 4