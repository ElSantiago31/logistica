# -*- coding: utf-8 -*-
"""Fix v2: 500 en GET /api/operators/ al filtrar por rol (chips del modal).

Bug: query exterior hace JOIN con Operator y el subquery assigned_sq tambien
usa Operator -> SQLAlchemy auto-correlaciona y elimina el FROM del subquery.
Solucion: aliased(Operator) dentro del subquery (nunca se auto-correlaciona).
"""
import io
import os
import sys

BACKEND = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
TARGET = os.path.join(BACKEND, "app", "services", "operators.py")

src = io.open(TARGET, encoding="utf-8").read()

if "op_sq = aliased(Operator)" in src:
    print("Ya parcheado (v2), nada que hacer.")
    sys.exit(0)

OLD_SQ = (
    "        if exclude_event_uuid:\n"
    "            assigned_sq = select(Operator.user_id).join(\n"
    "                EventAssignment, EventAssignment.operator_id == Operator.id\n"
    "            ).where(\n"
    "                EventAssignment.event_id == exclude_event_uuid\n"
    "            )"
)

NEW_SQ = (
    "        if exclude_event_uuid:\n"
    "            # Alias obligatorio: el query exterior puede hacer JOIN con\n"
    "            # Operator (filtros de rol/educacion de los chips). Sin alias\n"
    "            # SQLAlchemy auto-correlaciona y elimina el FROM de este\n"
    "            # subquery -> InvalidRequestError -> 500. Con alias queda\n"
    "            # autocontenido y nunca se correlaciona.\n"
    "            from sqlalchemy.orm import aliased\n"
    "            op_sq = aliased(Operator)\n"
    "            assigned_sq = select(op_sq.user_id).join(\n"
    "                EventAssignment, EventAssignment.operator_id == op_sq.id\n"
    "            ).where(\n"
    "                EventAssignment.event_id == exclude_event_uuid\n"
    "            )"
)

OLD_TAIL = (
    "            # Correlacionar SOLO contra User. Sin esto, cuando el query\n"
    "            # exterior hace JOIN con Operator (filtros de rol/educacion de\n"
    "            # los chips), SQLAlchemy auto-correlaciona y elimina el FROM del\n"
    "            # subquery -> InvalidRequestError -> 500 al filtrar por rol.\n"
    "            assigned_sq = assigned_sq.correlate(User)\n"
)

NEW_TAIL = ""

if OLD_SQ not in src:
    print("ERROR: bloque del subquery no encontrado.")
    sys.exit(1)

src = src.replace(OLD_SQ, NEW_SQ, 1)
src = src.replace(OLD_TAIL, NEW_TAIL, 1)

io.open(TARGET, "w", encoding="utf-8", newline="").write(src)

chk = io.open(TARGET, encoding="utf-8").read()
ok = "op_sq = aliased(Operator)" in chk and "correlate(User)" not in chk
print("PATCH v2 OK:", "APLICADO" if ok else "FALLO")
sys.exit(0 if ok else 1)