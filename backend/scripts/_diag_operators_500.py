# -*- coding: utf-8 -*-
"""Diagnóstico: 500 en GET /api/operators/ al usar chips del modal "+ Asignar".

1. Extrae la URL que arma searchOperators() en event_detail.html.
2. Llama get_operators() con esos mismos filtros contra una BD SQLite en
   memoria para reproducir la excepción real del 500.
"""
import asyncio
import io
import os
import re
import sys
import traceback

BACKEND = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, BACKEND)
os.chdir(BACKEND)

# Registrar TODOS los modelos en Base.metadata ANTES de create_all.
import app.models  # noqa: F401,E402

# 1) URL que arma el frontend
tpl = io.open(
    os.path.join(BACKEND, "app", "templates", "admin", "event_detail.html"),
    encoding="utf-8",
).read()
m = re.search(r"let url=`/api/operators/[^`]*`", tpl)
print("URL frontend:", m.group(0) if m else "NO ENCONTRADA")

from app.database import Base
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker


async def main():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    Session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    from datetime import datetime, timezone
    from app.models.users import User
    from app.models.operators import Operator
    from app.models.roles import Role
    from app.models.events import Event, EventAssignment
    from app.services.operators import get_operators

    async with Session() as db:
        role = Role(name="Mesero", slug="mesero")
        db.add(role)
        await db.flush()
        u = User(
            email="op@test.com", password_hash="x", first_name="Op", last_name="Uno",
            user_type="operator", is_active=True, is_approved=True, document_number="123",
        )
        db.add(u)
        await db.flush()
        op = Operator(user_id=u.id, experience_roles='["%s"]' % role.id, education_level="secundaria")
        db.add(op)
        ev = Event(
            name="E", location="Bogotá",
            start_date=datetime(2026, 11, 10, 8, tzinfo=timezone.utc),
            end_date=datetime(2026, 11, 11, 18, tzinfo=timezone.utc),
        )
        db.add(ev)
        await db.flush()
        db.add(EventAssignment(event_id=ev.id, operator_id=op.id, role_id=role.id, status="invited", stage="evento"))
        await db.commit()

        eid = str(ev.id)

        casos = {
            "A sin-filtros": dict(exclude_event_id=eid, exclude_stage="evento"),
            "B chip-rol": dict(experience_role_id=str(role.id), exclude_event_id=eid, exclude_stage="evento"),
            "C chip-rol+edu": dict(experience_role_id=str(role.id), education_level="tecnico",
                                   exclude_event_id=eid, exclude_stage="evento"),
            "D role_level": dict(role_level="1,2", exclude_event_id=eid, exclude_stage="evento"),
            "E chip-rol+filtro-vacio": dict(experience_role_id=str(role.id), city="bogota",
                                            exclude_event_id=eid, exclude_stage="evento"),
        }
        for nombre, kw in casos.items():
            try:
                r = await get_operators(db, 0, 100, True, True, **kw)
                print(nombre, "OK, total =", r[1])
            except Exception as e:
                print(nombre, "FALLA:", type(e).__name__, str(e)[:300])

    await engine.dispose()


asyncio.run(main())