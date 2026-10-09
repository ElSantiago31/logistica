# -*- coding: utf-8 -*-
"""Tests de asignación multi-evento con solapamiento de fechas.

Decisión de negocio (2026-10): un operador PUEDE estar asignado a varios
eventos cuyas fechas se solapen. El check de double-booking que antes
bloqueaba la asignación (enviaba al operador a ``unavailable``) se quitó
de ``services/events.py::assign_operators``. El solapamiento sigue
reportándose como aviso informativo (``available: false``) en
``list_available_operators`` para el dashboard del coordinador.

Reglas que siguen vigentes (cubiertas en otras suites):
- RUT vencido bloquea (test_rut_deadline.py).
- Duplicado dentro del mismo evento+etapa se ignora silenciosamente.
"""
import uuid
from datetime import datetime, timezone

from sqlalchemy import select

from app.models.events import Event, EventAssignment
from app.models.operators import Operator
from app.models.users import User
from app.services.events import assign_operators, list_available_operators


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _mk_user(db, *, first="Juan", last="Perez"):
    u = User(
        email=f"{uuid.uuid4().hex[:10]}@test.com",
        password_hash="x",
        first_name=first,
        last_name=last,
        document_number=f"79{uuid.uuid4().int % 10**8:08d}",
        user_type="operator",
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


async def _mk_event(db, *, n=0, start=None, end=None, status="published"):
    e = Event(
        name=f"Evento Multi {n}",
        location="Bogota",
        start_date=start or datetime(2026, 3, 10, 8, 0, tzinfo=timezone.utc),
        end_date=end or datetime(2026, 3, 10, 18, 0, tzinfo=timezone.utc),
        status=status,
    )
    db.add(e)
    await db.flush()
    return e


async def _count_assignments(db, operator_id) -> int:
    rows = (await db.execute(
        select(EventAssignment).where(EventAssignment.operator_id == operator_id)
    )).scalars().all()
    return len(rows)


# ---------------------------------------------------------------------------
# Asignación con solapamiento — ahora PERMITIDA
# ---------------------------------------------------------------------------

class TestMultiEventAssignment:
    async def test_asignacion_con_fechas_identicas(self, db):
        """Mismo día exacto en dos eventos → ambas asignaciones se crean."""
        op = await _mk_operator(db, first="Doble", last="Turno")
        ev_a = await _mk_event(db, n=1)
        ev_b = await _mk_event(db, n=2)  # mismas fechas que ev_a

        a1, un1 = await assign_operators(db, ev_a.id, [op.id])
        a2, un2 = await assign_operators(db, ev_b.id, [op.id])
        await db.commit()

        assert len(a1) == 1
        assert len(a2) == 1, "El solapamiento total NO debe bloquear la 2ª asignación"
        assert un1 == [] and un2 == []
        assert await _count_assignments(db, op.id) == 2

    async def test_asignacion_con_solapamiento_parcial(self, db):
        """Evento B termina después de que empieza A → se permite igual."""
        op = await _mk_operator(db, first="Parcial", last="Overlap")
        ev_a = await _mk_event(
            db, n=3,
            start=datetime(2026, 4, 1, 8, 0, tzinfo=timezone.utc),
            end=datetime(2026, 4, 2, 18, 0, tzinfo=timezone.utc),
        )
        ev_b = await _mk_event(
            db, n=4,
            start=datetime(2026, 4, 2, 8, 0, tzinfo=timezone.utc),   # solapa el 2/4
            end=datetime(2026, 4, 3, 18, 0, tzinfo=timezone.utc),
        )

        a1, _ = await assign_operators(db, ev_a.id, [op.id])
        a2, un2 = await assign_operators(db, ev_b.id, [op.id])
        await db.commit()

        assert len(a1) == 1 and len(a2) == 1
        assert un2 == [], "El solapamiento parcial NO debe reportar unavailable"

    async def test_asignacion_sobre_evento_in_progress(self, db):
        """Conflicto con evento ya iniciado (in_progress) → también permitido."""
        op = await _mk_operator(db, first="En", last="Curso")
        ev_a = await _mk_event(db, n=5, status="in_progress")
        ev_b = await _mk_event(db, n=6)  # solapa con ev_a

        _, un1 = await assign_operators(db, ev_a.id, [op.id])
        a2, un2 = await assign_operators(db, ev_b.id, [op.id])
        await db.commit()

        assert un1 == []
        assert len(a2) == 1 and un2 == []

    async def test_duplicado_mismo_evento_y_etapa_sigue_ignorado(self, db):
        """Regla intacta: re-asignar al MISMO evento+etapa no duplica fila."""
        op = await _mk_operator(db, first="Sin", last="Duplicar")
        ev = await _mk_event(db, n=7)

        a1, _ = await assign_operators(db, ev.id, [op.id])
        a2, _ = await assign_operators(db, ev.id, [op.id])
        await db.commit()

        assert len(a1) == 1
        assert len(a2) == 0, "No debe crear una 2ª fila para el mismo evento+etapa"
        assert await _count_assignments(db, op.id) == 1

    async def test_list_available_marca_conflicto_como_aviso(self, db):
        """El aviso informativo (available=false) se mantiene en el directorio."""
        op = await _mk_operator(db, first="Aviso", last="Solapa")
        ev_a = await _mk_event(db, n=8)
        ev_b = await _mk_event(db, n=9)  # mismas fechas

        await assign_operators(db, ev_a.id, [op.id])
        await db.commit()

        listings = await list_available_operators(db, ev_b.id)
        mine = [x for x in listings if x["operator_id"] == str(op.id)]
        assert len(mine) == 1
        # El solapamiento se REPORTA pero no excluye al operador del listado.
        assert mine[0]["available"] is False
        assert mine[0]["conflict_event_id"] == str(ev_a.id)

        # Y pese al aviso, la asignación al evento B funciona.
        a2, un2 = await assign_operators(db, ev_b.id, [op.id])
        await db.commit()
        assert len(a2) == 1 and un2 == []