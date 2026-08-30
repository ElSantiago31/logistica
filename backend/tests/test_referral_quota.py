# -*- coding: utf-8 -*-
"""Tests para la atribución de cupos por referido (F11 del plan).

Cubre las reglas R1/R2/R3 acordadas con producto:
- R1: el coordinador explícito SIEMPRE gana; el referido nunca lo pisa.
- R2: sin referente y sin coordinador explícito → campos quedan NULL.
- R3: solo asignaciones NUEVAS; nunca backfill de existentes.

Puntos de aplicación verificados:
- services/events.py::assign_operators (asignación manual admin/staff).
- services/operator_import.py::_create_assignment (import Excel).
- services/referrals.py::get_referrer_operator_of (helper).
"""
import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import select

from app.models.events import Event, EventAssignment
from app.models.operators import Operator
from app.models.referrals import Referral, ReferralCode
from app.models.users import User
from app.services.events import assign_operators
from app.services.referrals import (
    create_code_for_operator,
    get_referrer_operator_of,
    register_referral,
)


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
        name=f"Evento F11 Test {n}",
        location="Bogota",
        start_date=datetime(2026, 1, 10, 8, 0, tzinfo=timezone.utc),
        end_date=datetime(2026, 1, 10, 18, 0, tzinfo=timezone.utc),
    )
    db.add(e)
    await db.flush()
    return e


async def _mk_referral(db, *, referrer: Operator, referred: Operator):
    """Crea código + relación de referido entre dos operadores."""
    sa = await _mk_user(db, user_type="admin", first="Super", last="Admin")
    rc = await create_code_for_operator(db, operator_id=referrer.id, created_by=sa.id)
    await register_referral(
        db, code=rc.code, referred_operator_id=referred.id, commit=False,
    )
    return rc


async def _get_assignment(db, event_id, operator_id) -> EventAssignment:
    return await db.scalar(
        select(EventAssignment).where(
            EventAssignment.event_id == event_id,
            EventAssignment.operator_id == operator_id,
        )
    )


# ---------------------------------------------------------------------------
# Helper get_referrer_operator_of
# ---------------------------------------------------------------------------

class TestGetReferrerOperatorOf:
    async def test_retorna_referente_cuando_existe(self, db):
        referrer = await _mk_operator(db, first="Santiago", last="Gomez")
        referred = await _mk_operator(db, first="Pepito", last="Perez")
        await _mk_referral(db, referrer=referrer, referred=referred)

        got = await get_referrer_operator_of(db, referred.id)
        assert got is not None
        assert got.id == referrer.id

    async def test_retorna_none_cuando_no_hay_referente(self, db):
        op = await _mk_operator(db, first="Libre", last="SinRef")
        assert await get_referrer_operator_of(db, op.id) is None


# ---------------------------------------------------------------------------
# assign_operators (services/events.py) — reglas R1/R2/R3
# ---------------------------------------------------------------------------

class TestAssignOperatorsF11:
    async def test_r1_coordinador_explicito_gana(self, db):
        """El admin asigna con coordinador explícito → el referente NO pisa."""
        referrer = await _mk_operator(db, first="Santiago", last="Gomez")
        referred = await _mk_operator(db, first="Pepito", last="Perez")
        explicit = await _mk_operator(db, first="Maria", last="Lara")
        await _mk_referral(db, referrer=referrer, referred=referred)
        event = await _mk_event(db, n=1)

        assignments, _unavailable = await assign_operators(
            db, event.id, [referred.id],
            programmed_by_operator_id=explicit.id,
        )
        await db.commit()

        a = await _get_assignment(db, event.id, referred.id)
        assert a.programmed_by_operator_id == explicit.id
        assert a.admitted_by_operator_id == explicit.id
        assert a.programmed_by == "MARIA LARA"
        assert a.admitted_by == "MARIA LARA"

    async def test_r2_referente_es_estampado_cuando_no_hay_explicito(self, db):
        """Sin coordinador explícito → el referente se estampa (F11)."""
        referrer = await _mk_operator(db, first="Santiago", last="Gomez")
        referred = await _mk_operator(db, first="Pepito", last="Perez")
        await _mk_referral(db, referrer=referrer, referred=referred)
        event = await _mk_event(db, n=2)

        assignments, _unavailable = await assign_operators(db, event.id, [referred.id])
        await db.commit()

        a = await _get_assignment(db, event.id, referred.id)
        assert a.programmed_by_operator_id == referrer.id
        assert a.admitted_by_operator_id == referrer.id
        assert a.programmed_by == "SANTIAGO GOMEZ"
        assert a.admitted_by == "SANTIAGO GOMEZ"

    async def test_r2_sin_referente_y_sin_explicito_queda_null(self, db):
        """Operador sin referente asignado sin coordinador → campos NULL."""
        op = await _mk_operator(db, first="Libre", last="SinRef")
        event = await _mk_event(db, n=3)

        assignments, _unavailable = await assign_operators(db, event.id, [op.id])
        await db.commit()

        a = await _get_assignment(db, event.id, op.id)
        assert a.programmed_by_operator_id is None
        assert a.admitted_by_operator_id is None
        assert a.programmed_by is None
        assert a.admitted_by is None

    async def test_mezcla_referido_y_libre_en_mismo_lote(self, db):
        """El fallback es por-operador: no filtra entre iteraciones del lote."""
        referrer = await _mk_operator(db, first="Santiago", last="Gomez")
        referred = await _mk_operator(db, first="Pepito", last="Perez")
        free = await _mk_operator(db, first="Ana", last="Rios")
        await _mk_referral(db, referrer=referrer, referred=referred)
        event = await _mk_event(db, n=4)

        assignments, _unavailable = await assign_operators(
            db, event.id, [referred.id, free.id]
        )
        await db.commit()

        a_ref = await _get_assignment(db, event.id, referred.id)
        a_free = await _get_assignment(db, event.id, free.id)
        assert a_ref.programmed_by_operator_id == referrer.id
        assert a_ref.programmed_by == "SANTIAGO GOMEZ"
        assert a_free.programmed_by_operator_id is None
        assert a_free.programmed_by is None

    async def test_user_id_tambien_resuelve_referido(self, db):
        """El frontend envía user_id; el fallback debe funcionar igual."""
        referrer = await _mk_operator(db, first="Santiago", last="Gomez")
        referred = await _mk_operator(db, first="Pepito", last="Perez")
        await _mk_referral(db, referrer=referrer, referred=referred)
        event = await _mk_event(db, n=5)

        assignments, _unavailable = await assign_operators(
            db, event.id, [referred.user_id]
        )
        await db.commit()

        a = await _get_assignment(db, event.id, referred.id)
        assert a.programmed_by_operator_id == referrer.id
        assert a.programmed_by == "SANTIAGO GOMEZ"


# ---------------------------------------------------------------------------
# Importador Excel (operator_import.py) — reglas R1/R3
# ---------------------------------------------------------------------------

class TestImportF11:
    async def test_r1_excel_con_coordinador_gana(self, db):
        """Fila con coordinador explícito → se respeta (sin importar referidos)."""
        from app.services.operator_import import _create_assignment

        referrer = await _mk_operator(db, first="Santiago", last="Gomez")
        referred = await _mk_operator(db, first="Pepito", last="Perez")
        explicit = await _mk_operator(db, first="Maria", last="Lara")
        await _mk_referral(db, referrer=referrer, referred=referred)
        event = await _mk_event(db, n=6)
        await db.commit()

        await _create_assignment(
            db, event.id, referred.id, role_id=None,
            coord_op_id=explicit.id, coord_display="MARIA LARA",
        )
        await db.commit()

        a = await _get_assignment(db, event.id, referred.id)
        assert a.programmed_by_operator_id == explicit.id
        assert a.programmed_by == "MARIA LARA"

    async def test_r2_excel_sin_coordinado_usa_referente(self, db):
        """Fila SIN coordinador y operador CON referente → referente estampado."""
        from app.services.operator_import import _create_assignment

        referrer = await _mk_operator(db, first="Santiago", last="Gomez")
        referred = await _mk_operator(db, first="Pepito", last="Perez")
        await _mk_referral(db, referrer=referrer, referred=referred)
        event = await _mk_event(db, n=7)
        await db.commit()

        await _create_assignment(
            db, event.id, referred.id, role_id=None,
            coord_op_id=None, coord_display=None,
        )
        await db.commit()

        a = await _get_assignment(db, event.id, referred.id)
        assert a.programmed_by_operator_id == referrer.id
        assert a.programmed_by == "SANTIAGO GOMEZ"
        assert a.admitted_by == "SANTIAGO GOMEZ"

    async def test_r2_excel_sin_coordinador_sin_referente_queda_null(self, db):
        """Fila sin coordinador y operador sin referente → NULL."""
        from app.services.operator_import import _create_assignment

        op = await _mk_operator(db, first="Libre", last="SinRef")
        event = await _mk_event(db, n=8)
        await db.commit()

        await _create_assignment(
            db, event.id, op.id, role_id=None,
            coord_op_id=None, coord_display=None,
        )
        await db.commit()

        a = await _get_assignment(db, event.id, op.id)
        assert a.programmed_by_operator_id is None
        assert a.programmed_by is None

    async def test_r3_reimport_no_cambia_asignacion_existente(self, db):
        """UPDATE de fila existente no re-estampa coordinador (R3: sin backfill)."""
        from app.services.operator_import import (
            _create_assignment,
            _update_assignment_coordinator,
        )

        referrer = await _mk_operator(db, first="Santiago", last="Gomez")
        referred = await _mk_operator(db, first="Pepito", last="Perez")
        await _mk_referral(db, referrer=referrer, referred=referred)
        event = await _mk_event(db, n=9)
        await db.commit()

        # Primera importación SIN coordinador → referente estampado (F11).
        await _create_assignment(
            db, event.id, referred.id, role_id=None,
            coord_op_id=None, coord_display=None,
        )
        await db.commit()
        first = await _get_assignment(db, event.id, referred.id)
        assert first.programmed_by == "SANTIAGO GOMEZ"

        # Re-import con Excel SIN coordinador → update no toca nada.
        changed = await _update_assignment_coordinator(
            db, event.id, referred.id, coord_op_id=None, coord_display=None,
        )
        await db.commit()
        assert changed is False
        second = await _get_assignment(db, event.id, referred.id)
        assert second.programmed_by == "SANTIAGO GOMEZ"