# -*- coding: utf-8 -*-
"""Parche puntual: tests de cambio de rol en check-in."""
import sys, pathlib

P = pathlib.Path(__file__).resolve().parent.parent / "tests" / "test_checkin_overquota.py"
src = P.read_text(encoding="utf-8")

def rep(old, new, count=1):
    global src
    if old not in src:
        print(f"NO ENCONTRADO:\n{old[:120]}...")
        sys.exit(1)
    src = src.replace(old, new, count)

# 1) import Role
rep(
"""from app.models.events import Event, EventAssignment, EventCoordinatorQuota
from app.models.sync import AttendanceLog""",
"""from app.models.events import Event, EventAssignment, EventCoordinatorQuota
from app.models.roles import Role
from app.models.sync import AttendanceLog""")

# 2) fixture: roles + assignment con rol
rep(
"""    db.add(EventCoordinatorQuota(
        event_id=event.id, coordinator="XIMENA", quota=1,
    ))
    a1 = EventAssignment(
        event_id=event.id, operator_id=o1.id, status="checked_in",
        admitted_by="XIMENA",
    )""",
"""    db.add(EventCoordinatorQuota(
        event_id=event.id, coordinator="XIMENA", quota=1,
    ))
    # Roles para probar el cambio de rol en check-in
    r_brig = Role(name="Brigadista Test", slug="brig-test", hierarchy_level=5)
    r_log = Role(name="Logistica Test", slug="log-test", hierarchy_level=5)
    db.add_all([r_brig, r_log])
    await db.flush()
    a1 = EventAssignment(
        event_id=event.id, operator_id=o1.id, status="checked_in",
        admitted_by="XIMENA", role_id=r_brig.id,
    )""")

# 3) fixture: retornar roles/assignment
rep(
"""        "token": token,
        "operator2": o2,
        "admin": admin,
    }""",
"""        "token": token,
        "operator2": o2,
        "admin": admin,
        "role_logistica": r_log,
        "assignment_checked": a1,
    }""")

# 4) CSV: 12 columnas + Cambio de Rol
rep(
"""    header = rows[0]
    assert len(header) == 11, f"deben ser 11 columnas, hay {len(header)}\"""",
"""    header = rows[0]
    assert len(header) == 12, f"deben ser 12 columnas, hay {len(header)}"
    assert "Cambio de Rol" in header, f"falta columna Cambio de Rol: {header}\"""")

# 5) CSV: assertions de Rol + nueva test de cambio de rol
rep(
"""    metodo_idx = header.index("Método")
    assert o1_row[metodo_idx] == "Manual"
""",
"""    metodo_idx = header.index("Método")
    assert o1_row[metodo_idx] == "Manual"
    rol_idx = header.index("Rol")
    assert o1_row[rol_idx] == "Brigadista Test"
    cr_idx = header.index("Cambio de Rol")
    assert o1_row[cr_idx] == "", f"sin cambio de rol deberia ser vacio: {o1_row[cr_idx]!r}"


@pytest.mark.asyncio
async def test_change_role_endpoint_and_csv(client, overquota_env):
    \"\"\"PATCH /assignments/{id}/role cambia el rol y lo refleja en el CSV.\"\"\"
    token = overquota_env["token"]
    aid = str(overquota_env["assignment_checked"].id)
    new_role_id = str(overquota_env["role_logistica"].id)

    resp = await client.patch(
        f"/api/sync/assignments/{aid}/role",
        headers={"Authorization": f"Bearer {token}"},
        json={"role_id": new_role_id, "reason": "test"},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["status"] == "role_changed"
    assert data["old_role"] == "Brigadista Test"
    assert data["new_role"] == "Logistica Test"

    # El log de asistencia queda anotado (visible en /attendance)
    resp2 = await client.get(
        f"/api/sync/events/{overquota_env['event_id']}/attendance",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp2.status_code == 200
    rec = next(r for r in resp2.json()["records"] if "90002" in r["operator_name"])
    assert rec["role_change"] == "Brigadista Test->Logistica Test"

    # CSV: Rol = nuevo, Cambio de Rol = "OLD -> NEW"
    resp3 = await client.get(
        f"/api/sync/events/{overquota_env['event_id']}/attendance-log.csv",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp3.status_code == 200
    text = resp3.text.lstrip("\\ufeff")
    rows = list(csv.reader(StringIO(text), delimiter=";"))
    header = rows[0]
    o1_row = next(r for r in rows[1:] if "90002" in r)
    assert o1_row[header.index("Rol")] == "Logistica Test"
    assert o1_row[header.index("Cambio de Rol")] == "Brigadista Test -> Logistica Test"

    # Idempotencia: mismo rol otra vez -> unchanged
    resp4 = await client.patch(
        f"/api/sync/assignments/{aid}/role",
        headers={"Authorization": f"Bearer {token}"},
        json={"role_id": new_role_id},
    )
    assert resp4.status_code == 200
    assert resp4.json()["status"] == "unchanged"
""")

P.write_text(src, encoding="utf-8")
print("OK: parche tests aplicado")