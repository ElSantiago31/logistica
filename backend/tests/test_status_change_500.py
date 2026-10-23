# -*- coding: utf-8 -*-
"""Tests de regresión: cambio de estado de asignación (500 con roles multi-etapa).

Bug: `PATCH /api/whatsapp/assignments/{id}/status` devolvía 500 cuando el
rol de la asignación tenía EventStaffNeeds en MÁS DE UNA etapa (previa,
avanzada, evento, desmontaje). `scalar_one_or_none()` lanzaba
``MultipleResultsFound`` dentro de
``services/whatsapp.py::update_assignment_status``.

Fix: filtrar por la etapa de la asignación con ``.scalars().first()`` y
fallback a cualquier etapa (mismo patrón que ``delete_assignment``).
"""
import uuid
from datetime import datetime, timezone

from app.models.events import Event, EventStaffNeed
from app.models.roles import Role
from app.services.whatsapp import update_assignment_status

from tests.test_multi_event_assignment import _mk_operator, _mk_event


class TestStatusChangeMultiStageRole:
    async def test_cambio_estado_con_rol_en_dos_etapas(self, db):
        """Rol con needs en 2 etapas: el cambio de estado no debe lanzar
        MultipleResultsFound (500) y debe ajustar quantity_confirmed
        del need de la etapa correcta."""
        op = await _mk_operator(db, first="Dos", last="Etapas")
        ev = await _mk_event(db, n=20)

        slug = uuid.uuid4().hex[:10]
        role = Role(name=f"Rol Multi {slug}", slug=f"rm-{slug}")
        db.add(role)
        await db.flush()

        # Needs del mismo rol en 2 etapas distintas → antes: 500.
        need_evento = EventStaffNeed(
            event_id=ev.id, role_id=role.id, quantity_needed=5, stage="evento",
        )
        need_previa = EventStaffNeed(
            event_id=ev.id, role_id=role.id, quantity_needed=2, stage="previa",
        )
        db.add_all([need_evento, need_previa])
        await db.flush()

        # Asignación en etapa "evento" con ese rol, estado inicial invited.
        from app.models.events import EventAssignment
        assignment = EventAssignment(
            event_id=ev.id,
            operator_id=op.id,
            role_id=role.id,
            status="invited",
            stage="evento",
        )
        db.add(assignment)
        await db.flush()

        # invited → confirmed (antes: MultipleResultsFound → 500)
        result = await update_assignment_status(db, assignment.id, "confirmed")
        await db.commit()
        assert result is not None
        assert result.status == "confirmed"

        # El need de la etapa "evento" ganó el confirmado; el de "previa" no.
        await db.refresh(need_evento)
        await db.refresh(need_previa)
        assert need_evento.quantity_confirmed == 1
        assert need_previa.quantity_confirmed == 0

        # confirmed → standby (pierde el confirmado)
        result = await update_assignment_status(db, assignment.id, "standby")
        await db.commit()
        assert result.status == "standby"
        await db.refresh(need_evento)
        assert need_evento.quantity_confirmed == 0

    async def test_cambio_estado_rol_unica_etapa(self, db):
        """Caso simple (una sola etapa) sigue funcionando igual que antes."""
        op = await _mk_operator(db, first="Una", last="Etapa")
        ev = await _mk_event(db, n=21)

        slug = uuid.uuid4().hex[:10]
        role = Role(name=f"Rol Simple {slug}", slug=f"rs-{slug}")
        db.add(role)
        await db.flush()

        need = EventStaffNeed(
            event_id=ev.id, role_id=role.id, quantity_needed=3, stage="evento",
        )
        db.add(need)
        await db.flush()

        from app.models.events import EventAssignment
        assignment = EventAssignment(
            event_id=ev.id,
            operator_id=op.id,
            role_id=role.id,
            status="invited",
            stage="evento",
        )
        db.add(assignment)
        await db.flush()

        result = await update_assignment_status(db, assignment.id, "confirmed")
        await db.commit()
        assert result.status == "confirmed"
        await db.refresh(need)
        assert need.quantity_confirmed == 1

    async def test_cambio_estado_sin_rol(self, db):
        """Asignación sin role_id (quick add): no debe tocar ningún need."""
        op = await _mk_operator(db, first="Sin", last="Rol")
        ev = await _mk_event(db, n=22)

        from app.models.events import EventAssignment
        assignment = EventAssignment(
            event_id=ev.id,
            operator_id=op.id,
            status="invited",
        )
        db.add(assignment)
        await db.flush()

        result = await update_assignment_status(db, assignment.id, "rejected")
        await db.commit()
        assert result.status == "rejected"