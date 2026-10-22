# -*- coding: utf-8 -*-
"""Fix del 500 en GET /api/operators/ con filtros del modal "+ Asignar".

Dos bugs en get_operators (app/services/operators.py):
1. exclude_event_id llega como str del query param y se compara contra la
   columna UUID -> AttributeError ('str' object has no attribute 'hex').
2. Cuando los chips añaden filtros (rol/educación/ciudad), el query exterior
   hace JOIN con Operator y SQLAlchemy auto-correlaciona el subquery
   assigned_sq eliminando su FROM -> InvalidRequestError.

Solución: parsear el UUID y forzar assigned_sq.correlate(User).
"""
import io
import os
import sys

BACKEND = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
TARGET = os.path.join(BACKEND, "app", "services", "operators.py")

src = io.open(TARGET, encoding="utf-8").read()

OLD = '''    # Exclude already assigned to event
    if exclude_event_id:
        from app.models.events import EventAssignment
        assigned_sq = select(Operator.user_id).join(
            EventAssignment, EventAssignment.operator_id == Operator.id
        ).where(
            EventAssignment.event_id == exclude_event_id
        )
        # Solo excluye de la etapa indicada: un operador en OTRA etapa sigue
        # apareciendo y puede reasignarse (= doble turno, permitido).
        if exclude_stage:
            assigned_sq = assigned_sq.where(EventAssignment.stage == exclude_stage)
        query = query.where(User.id.notin_(assigned_sq))
        count_query = count_query.where(User.id.notin_(assigned_sq))'''

NEW = '''    # Exclude already assigned to event
    if exclude_event_id:
        from app.models.events import EventAssignment
        # El frontend envía el id del evento como string: normalizarlo a UUID
        # antes de compararlo con la columna UUID (evita AttributeError 'str'
        # object has no attribute 'hex' -> 500).
        try:
            exclude_event_uuid = uuid.UUID(str(exclude_event_id))
        except (ValueError, TypeError, AttributeError):
            exclude_event_uuid = None
        if exclude_event_uuid:
            assigned_sq = select(Operator.user_id).join(
                EventAssignment, EventAssignment.operator_id == Operator.id
            ).where(
                EventAssignment.event_id == exclude_event_uuid
            )
            # Solo excluye de la etapa indicada: un operador en OTRA etapa sigue
            # apareciendo y puede reasignarse (= doble turno, permitido).
            if exclude_stage:
                assigned_sq = assigned_sq.where(EventAssignment.stage == exclude_stage)
            # Correlacionar SOLO contra User. Sin esto, cuando el query
            # exterior hace JOIN con Operator (filtros de rol/educación de
            # los chips), SQLAlchemy auto-correlaciona y elimina el FROM del
            # subquery -> InvalidRequestError -> 500 al filtrar por rol.
            assigned_sq = assigned_sq.correlate(User)
            query = query.where(User.id.notin_(assigned_sq))
            count_query = count_query.where(User.id.notin_(assigned_sq))'''

if "exclude_event_uuid" in src:
    print("Ya parcheado, nada que hacer.")
    sys.exit(0)

if OLD not in src:
    print("ERROR: bloque original no encontrado — revisar manualmente.")
    sys.exit(1)

src = src.replace(OLD, NEW, 1)
io.open(TARGET, "w", encoding="utf-8", newline="").write(src)

chk = io.open(TARGET, encoding="utf-8").read()
ok = "exclude_event_uuid" in chk and "correlate(User)" in chk
print("PATCH OK — verificación:", "APLICADO" if ok else "FALLÓ")
sys.exit(0 if ok else 1)