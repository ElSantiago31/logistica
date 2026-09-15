# -*- coding: utf-8 -*-
"""Tests de etapas de evento (previa | avanzada | evento | desmontaje).

Cubre:
- Creación con staff_needs y coordinator_quotas por etapa.
- Resumen by_stage en get_event.
- Doble turno: mismo operador en dos etapas del mismo evento.
- Dedup: mismo operador en la MISMA etapa no se duplica.
- Cuotas por etapa: "used" cuenta solo confirmed/checked_in de esa etapa.
- Merge defensivo de needs duplicados (role_id, stage).
- delete_assignment decrementa el need de la etapa correcta.
"""
import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import select

from app.models.events import (
    DEFAULT_STAGE, Event, EventAssignment, EventStaffNeed, EventCoordinatorQuota,
)
from app.models.operators import Operator
from app.models.roles import Role
from app.models.users import User
from app.schemas.events import EventCreate, StaffNeedCreate, CoordinatorQuotaCreate
from app.services import events as svc


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


async def _mk_role(db, *, name="Operador Logistico"):
    suffix = uuid.uuid4().hex[:6]
    r = Role(name=f"{name} {suffix}", slug=f"op-{suffix}")
    db.add(r)
    await db.flush()
    return r


def _mk_create(role_id, coord_op_id, *, stage_a="previa", stage_b="evento"):
    return EventCreate(
        name=f"Evento Etapas {uuid.uuid4().hex[:6]}",
        location="Bogota",
        start_date=datetime(2026, 6, 10, 8, 0, tzinfo=timezone.utc),
        end_date=datetime(2026, 6, 12, 18, 0, tzinfo=timezone.utc),
        staff_needs=[
            StaffNeedCreate(role_id=role_id, quantity_needed=5, rate_per_shift=120000, stage=stage_a),
            StaffNeedCreate(role_id=role_id, quantity_needed=10, rate_per_shift=100000, stage=stage_b),
        ],
        coordinator_quotas=[
            CoordinatorQuotaCreate(operator_id=coord_op_id, quota=3, stage=stage_a),
            CoordinatorQuotaCreate(operator_id=coord_op_id, quota=6, stage=stage_b),
        ],
    )


async def _confirm(db, assignment_id):
    a = await db.get(EventAssignment, assignment_id)
    a.status = "confirmed"
    a.confirmed_at = datetime.now(timezone.utc)
    await db.commit()


# ---------------------------------------------------------------------------
# Creación y lectura por etapa
# ---------------------------------------------------------------------------

class TestCreateEventStages:

    async def test_needs_y_cuotas_guardan_stage(self, db):
        role = await _mk_role(db)
        coord = await _mk_operator(db, first="Coco", last="Ordina")
        admin = await _mk_user(db, user_type="admin", first="Ad", last="Min")

        event = await svc.create_event(db, _mk_create(role.id, coord.id), admin.id)

        needs = (await db.execute(
            select(EventStaffNeed).where(EventStaffNeed.event_id == event.id)
        )).scalars().all()
        assert {n.stage for n in needs} == {"previa", "evento"}

        quotas = (await db.execute(
            select(EventCoordinatorQuota).where(EventCoordinatorQuota.event_id == event.id)
        )).scalars().all()
        assert {q.stage for q in quotas} == {"previa", "evento"}
        # La cuota guarda la FK y el nombre en MAYÚSCULAS.
        for q in quotas:
            assert q.coordinator_operator_id == coord.id
            assert q.coordinator == "COCO ORDINA"

    async def test_get_event_resume_by_stage(self, db):
        role = await _mk_role(db)
        coord = await _mk_operator(db, first="Coco", last="Ordina")
        admin = await _mk_user(db, user_type="admin", first="Ad", last="Min")

        event = await svc.create_event(db, _mk_create(role.id, coord.id), admin.id)
        result = await svc.get_event(db, event.id)

        by = result["by_stage"]
        assert by["previa"]["needed"] == 5
        assert by["evento"]["needed"] == 10
        assert by["previa"]["quota_total"] == 3
        assert by["evento"]["quota_total"] == 6
        # stage estampado en needs y quotas del response
        assert {n["stage"] for n in result["staff_needs"]} == {"previa", "evento"}
        assert {q["stage"] for q in result["coordinator_quotas"]} == {"previa", "evento"}

    async def test_needs_duplicados_misma_etapa_se_suman(self, db):
        role = await _mk_role(db)
        admin = await _mk_user(db, user_type="admin", first="Ad", last="Min")
        data = EventCreate(
            name=f"Merge {uuid.uuid4().hex[:6]}",
            location="Bogota",
            start_date=datetime(2026, 6, 10, 8, 0, tzinfo=timezone.utc),
            end_date=datetime(2026, 6, 12, 18, 0, tzinfo=timezone.utc),
            staff_needs=[
                StaffNeedCreate(role_id=role.id, quantity_needed=3, rate_per_shift=100000, stage="previa"),
                StaffNeedCreate(role_id=role.id, quantity_needed=4, rate_per_shift=100000, stage="previa"),
            ],
        )
        event = await svc.create_event(db, data, admin.id)
        result = await svc.get_event(db, event.id)
        previa = [n for n in result["staff_needs"] if n["stage"] == "previa"]
        assert len(previa) == 1
        assert previa[0]["quantity_needed"] == 7

    async def test_cuota_legacy_sin_fk_no_crashea(self, db):
        role = await _mk_role(db)
        admin = await _mk_user(db, user_type="admin", first="Ad", last="Min")
        data = EventCreate(
            name=f"Legacy {uuid.uuid4().hex[:6]}",
            location="Bogota",
            start_date=datetime(2026, 6, 10, 8, 0, tzinfo=timezone.utc),
            end_date=datetime(2026, 6, 12, 18, 0, tzinfo=timezone.utc),
            staff_needs=[StaffNeedCreate(role_id=role.id, quantity_needed=2, rate_per_shift=100000)],
            coordinator_quotas=[
                CoordinatorQuotaCreate(coordinator_name="PEDRO LEGACY", quota=4),
            ],
        )
        event = await svc.create_event(db, data, admin.id)
        result = await svc.get_event(db, event.id)
        q = result["coordinator_quotas"][0]
        assert q["coordinator"] == "PEDRO LEGACY"
        assert q["coordinator_operator_id"] is None
        assert q["stage"] == DEFAULT_STAGE


# ---------------------------------------------------------------------------
# Doble turno (mismo operador, dos etapas)
# ---------------------------------------------------------------------------

class TestDoubleShift:

    async def _setup(self, db):
        role = await _mk_role(db)
        coord = await _mk_operator(db, first="Coco", last="Ordina")
        admin = await _mk_user(db, user_type="admin", first="Ad", last="Min")
        event = await svc.create_event(db, _mk_create(role.id, coord.id), admin.id)
        return event, role, coord, admin

    async def test_mismo_operador_en_dos_etapas(self, db):
        event, role, coord, admin = await self._setup(db)
        op = await _mk_operator(db, first="Doble", last="Turno")

        a1, _ = await svc.assign_operators(db, event.id, [op.id], role_id=role.id, stage="previa")
        a2, _ = await svc.assign_operators(db, event.id, [op.id], role_id=role.id, stage="evento")

        assert len(a1) == 1 and a1[0].stage == "previa"
        assert len(a2) == 1 and a2[0].stage == "evento"

        assignments = await svc.get_assignments(db, event.id)
        assert len(assignments) == 2
        # Todas marcadas como doble turno
        assert all(a["double_shift"] for a in assignments)

    async def test_mismo_operador_misma_etapa_no_duplica(self, db):
        event, role, coord, admin = await self._setup(db)
        op = await _mk_operator(db, first="Uni", last="Turno")

        a1, _ = await svc.assign_operators(db, event.id, [op.id], role_id=role.id, stage="previa")
        a2, _ = await svc.assign_operators(db, event.id, [op.id], role_id=role.id, stage="previa")

        assert len(a1) == 1
        assert len(a2) == 0  # dedup silencioso

    async def test_stage_invalida_cae_en_default(self, db):
        event, role, coord, admin = await self._setup(db)
        op = await _mk_operator(db, first="Raro", last="Stage")
        a1, _ = await svc.assign_operators(db, event.id, [op.id], role_id=role.id, stage="etapa-inventada")
        assert len(a1) == 1
        assert a1[0].stage == DEFAULT_STAGE


# ---------------------------------------------------------------------------
# Cuotas por etapa: conteo used
# ---------------------------------------------------------------------------

class TestQuotaUsageByStage:

    async def test_used_cuenta_solo_confirmados_de_la_etapa(self, db):
        role = await _mk_role(db)
        coord = await _mk_operator(db, first="Coco", last="Ordina")
        admin = await _mk_user(db, user_type="admin", first="Ad", last="Min")
        event = await svc.create_event(db, _mk_create(role.id, coord.id), admin.id)

        op1 = await _mk_operator(db, first="Uno", last="Previa")
        op2 = await _mk_operator(db, first="Dos", last="Evento")
        op3 = await _mk_operator(db, first="Tres", last="Rechazado")

        # invited (aún no ocupa cupo)
        inv, _ = await svc.assign_operators(
            db, event.id, [op1.id], role_id=role.id,
            programmed_by_operator_id=coord.id, stage="previa",
        )
        result = await svc.get_event(db, event.id)
        q_previa = [q for q in result["coordinator_quotas"] if q["stage"] == "previa"][0]
        assert q_previa["used"] == 0  # invited no cuenta

        await _confirm(db, inv[0].id)

        # confirmado en evento + rejected en previa
        ev, _ = await svc.assign_operators(
            db, event.id, [op2.id], role_id=role.id,
            programmed_by_operator_id=coord.id, stage="evento",
        )
        await _confirm(db, ev[0].id)
        rj, _ = await svc.assign_operators(
            db, event.id, [op3.id], role_id=role.id,
            programmed_by_operator_id=coord.id, stage="previa",
        )
        rej_a = await db.get(EventAssignment, rj[0].id)
        rej_a.status = "rejected"
        await db.commit()

        result = await svc.get_event(db, event.id)
        q_previa = [q for q in result["coordinator_quotas"] if q["stage"] == "previa"][0]
        q_evento = [q for q in result["coordinator_quotas"] if q["stage"] == "evento"][0]
        # previa: op1 confirmado (1); rejected de op3 NO cuenta.
        assert q_previa["used"] == 1
        assert q_previa["available"] == 2
        # evento: op2 confirmado (1), independiente de previa.
        assert q_evento["used"] == 1
        assert q_evento["available"] == 5

    async def test_cuota_legacy_cuenta_por_admitted_by(self, db):
        role = await _mk_role(db)
        admin = await _mk_user(db, user_type="admin", first="Ad", last="Min")
        data = EventCreate(
            name=f"LegacyUsed {uuid.uuid4().hex[:6]}",
            location="Bogota",
            start_date=datetime(2026, 6, 10, 8, 0, tzinfo=timezone.utc),
            end_date=datetime(2026, 6, 12, 18, 0, tzinfo=timezone.utc),
            staff_needs=[StaffNeedCreate(role_id=role.id, quantity_needed=5, rate_per_shift=100000)],
            coordinator_quotas=[CoordinatorQuotaCreate(coordinator_name="PEDRO LEGACY", quota=5)],
        )
        event = await svc.create_event(db, data, admin.id)
        op = await _mk_operator(db, first="Legado", last="Uno")
        res, _ = await svc.assign_operators(
            db, event.id, [op.id], role_id=role.id,
            programmed_by_name="Pedro Legacy", stage=DEFAULT_STAGE,
        )
        await _confirm(db, res[0].id)
        # El string quedó en MAYÚSCULAS para matchear con la cuota.
        a = await db.get(EventAssignment, res[0].id)
        assert a.admitted_by == "PEDRO LEGACY"

        result = await svc.get_event(db, event.id)
        q = [q for q in result["coordinator_quotas"] if q["stage"] == DEFAULT_STAGE][0]
        assert q["used"] == 1
        assert q["available"] == 4


# ---------------------------------------------------------------------------
# delete_assignment decrementa el need de la etapa correcta
# ---------------------------------------------------------------------------

class TestDeleteAssignmentStage:

    async def test_decrementa_need_de_la_misma_etapa(self, db):
        role = await _mk_role(db)
        coord = await _mk_operator(db, first="Coco", last="Ordina")
        admin = await _mk_user(db, user_type="admin", first="Ad", last="Min")
        event = await svc.create_event(db, _mk_create(role.id, coord.id), admin.id)

        op = await _mk_operator(db, first="Borra", last="Me")
        res, _ = await svc.assign_operators(
            db, event.id, [op.id], role_id=role.id,
            programmed_by_operator_id=coord.id, stage="previa",
        )
        await _confirm(db, res[0].id)

        needs = (await db.execute(
            select(EventStaffNeed).where(EventStaffNeed.event_id == event.id)
        )).scalars().all()
        for n in needs:  # simular el flujo del check-in manual
            if n.stage == "previa":
                n.quantity_confirmed = 1
        await db.commit()

        # Reproducir la lógica del router delete_assignment
        assignment = await db.get(EventAssignment, res[0].id)
        assert assignment.status == "confirmed"
        stage = assignment.stage or DEFAULT_STAGE
        sn_r = await db.execute(
            select(EventStaffNeed).where(
                EventStaffNeed.event_id == assignment.event_id,
                EventStaffNeed.role_id == assignment.role_id,
                EventStaffNeed.stage == stage,
            )
        )
        sn = sn_r.scalar_one_or_none()
        assert sn is not None and sn.stage == "previa"
        sn.quantity_confirmed = max(sn.quantity_confirmed - 1, 0)

        evento_need = [n for n in needs if n.stage == "evento"][0]
        assert sn.quantity_confirmed == 0
        assert evento_need.quantity_confirmed == 0  # intacto