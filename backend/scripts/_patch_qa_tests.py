# -*- coding: utf-8 -*-
"""Parche: agrega 4 tests de regresion al fix del 500 en quick-add."""
import io
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent  # backend/
T = BASE / "tests" / "test_quick_add.py"

REPLACEMENTS = [
    (
        "from app.models.events import Event\n"
        "from app.models.operators import Operator\n"
        "from app.models.users import User\n"
        "from app.services.auth import hash_password\n"
        "\n"
        "\n"
        "async def _mk_user(db, doc, user_type, is_active=True):\n",
        "from app.models.events import Event, EventAssignment\n"
        "from app.models.operators import Operator\n"
        "from app.models.users import User\n"
        "from app.services.auth import hash_password\n"
        "\n"
        "\n"
        "async def _mk_user(db, doc, user_type, is_active=True, doc_type=\"CC\"):\n",
    ),
    (
        "        first_name=\"Usr\",\n"
        "        last_name=doc,\n"
        "        user_type=user_type,\n"
        "        document_type=\"CC\",\n",
        "        first_name=\"Usr\",\n"
        "        last_name=doc,\n"
        "        user_type=user_type,\n"
        "        document_type=doc_type,\n",
    ),
]

TAIL_TESTS = '''

@pytest.mark.asyncio
async def test_quick_add_imported_cedula_type(client, qa_env, db):
    """Operador importado por Excel con tipo 'CEDULA' + quick-add con 'CC'
    -> 201 mode=existing (antes: 500 por violar UNIQUE del documento)."""
    imported_user = await _mk_user(db, "80010", "operator", doc_type="CEDULA")
    imported_op = Operator(user_id=imported_user.id, event_only=False)
    db.add(imported_op)
    await db.commit()

    res = await client.post(
        f"/api/events/{qa_env['event_id']}/quick-add",
        json=_payload("80010"),  # envia document_type="CC"
        headers={"Authorization": f"Bearer {qa_env['admin_token']}"},
    )
    assert res.status_code == 201, res.text
    assert res.json()["mode"] == "existing"


@pytest.mark.asyncio
async def test_quick_add_existing_doc_different_type(client, qa_env, db):
    """Operador guardado como CE + quick-add con CC -> 201 existing."""
    ce_user = await _mk_user(db, "80011", "operator", doc_type="CE")
    ce_op = Operator(user_id=ce_user.id, event_only=False)
    db.add(ce_op)
    await db.commit()

    payload = _payload("80011")
    payload["document_type"] = "CC"
    res = await client.post(
        f"/api/events/{qa_env['event_id']}/quick-add",
        json=payload,
        headers={"Authorization": f"Bearer {qa_env['admin_token']}"},
    )
    assert res.status_code == 201, res.text
    assert res.json()["mode"] == "existing"


@pytest.mark.asyncio
async def test_quick_add_passport_type_mismatch(client, qa_env, db):
    """Operador guardado como PA (importador Excel) + quick-add con PP
    -> 201 existing (antes: 500)."""
    pa_user = await _mk_user(db, "80012", "operator", doc_type="PA")
    pa_op = Operator(user_id=pa_user.id, event_only=False)
    db.add(pa_op)
    await db.commit()

    payload = _payload("80012")
    payload["document_type"] = "PP"
    res = await client.post(
        f"/api/events/{qa_env['event_id']}/quick-add",
        json=payload,
        headers={"Authorization": f"Bearer {qa_env['admin_token']}"},
    )
    assert res.status_code == 201, res.text
    assert res.json()["mode"] == "existing"


@pytest.mark.asyncio
async def test_quick_add_long_admin_name(client, qa_env, db):
    """admitted_by con nombre de admin > 100 chars -> 201 y truncado a <=100
    (regresion: antes [:200] sobre columna String(100) -> DataError -> 500)."""
    from sqlalchemy import select
    long_admin = User(
        id=uuid.uuid4(),
        email="longadmin@qa.test",
        password_hash=hash_password("secreto123"),
        first_name="Nombre" * 12,   # 72 chars
        last_name="Apellido" * 10,  # 80 chars
        user_type="admin",
        document_type="CC",
        document_number="80013",
        is_verified=True,
        is_approved=True,
        is_active=True,
    )
    db.add(long_admin)
    await db.commit()
    token = await _login(client, "80013")

    res = await client.post(
        f"/api/events/{qa_env['event_id']}/quick-add",
        json=_payload("999006"),
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 201, res.text

    row = await db.execute(
        select(EventAssignment).where(
            EventAssignment.id == uuid.UUID(res.json()["assignment_id"])
        )
    )
    assignment = row.scalar_one()
    assert assignment.admitted_by is not None
    assert len(assignment.admitted_by) <= 100
'''


def main():
    src = io.open(T, "r", encoding="utf-8").read()
    for old, new in REPLACEMENTS:
        if new in src:
            print("[tests] ya aplicado:", old.strip().splitlines()[0][:50])
            continue
        if old not in src:
            print("[tests] ERROR: bloque no encontrado:")
            print("   ", old.strip().splitlines()[0][:70])
            sys.exit(1)
        src = src.replace(old, new, 1)
        print("[tests] ok:", old.strip().splitlines()[0][:50])
    if "test_quick_add_imported_cedula_type" not in src:
        src = src.rstrip("\n") + "\n" + TAIL_TESTS
        print("[tests] ok: + 4 tests de regresion al final")
    else:
        print("[tests] ya aplicado: tail tests")
    io.open(T, "w", encoding="utf-8", newline="").write(src)
    print("PATCH TESTS COMPLETO")


if __name__ == "__main__":
    main()