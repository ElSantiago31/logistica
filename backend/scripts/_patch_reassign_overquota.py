# -*- coding: utf-8 -*-
"""Parche: permitir sobrecupo (force_overquota) en la reasignación de coordinador.

Problema: si TODOS los coordinadores de un evento están con el cupo lleno,
el modal de reasignación no tiene salida (solo lista vacía) y el endpoint
PATCH /api/sync/assignments/{id}/reassign devuelve 409 QUOTA_FULL sin
opción de forzar. El staff queda bloqueado para hacer check-in.

Fix (misma semántica que el check-in, donde force_overquota ya existe):
  Backend (sync.py):
    - /reassign acepta force_overquota=true y permite la cesión aunque el
      cupo destino esté lleno; marca overquota en respuesta + audit log.
  Frontend (checkin.html):
    - Modal de reasignación muestra botón "Dejar en sobrecupo" siempre
      (escape cuando no hay coordinadores con cupo).
    - confirmReassign y changeCoordinator ofrecen forzar tras 409 QUOTA_FULL.
  Tests (test_checkin_overquota.py):
    - test_reassign_force_overquota: 409 sin force / 200 + overquota con force.

Uso:  python scripts/_patch_reassign_overquota.py   (desde backend/)
"""
import io
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]


def patch_file(rel: str, replacements: list, must_apply: list = None) -> None:
    path = BACKEND / rel
    src = path.read_text(encoding="utf-8")
    for i, (old, new) in enumerate(replacements):
        if old not in src:
            if must_apply and i in must_apply:
                raise SystemExit(f"[FALLO] Anclaje #{i} no encontrado en {rel}:\n---\n{old}\n---")
            print(f"[aviso] anclaje #{i} ya aplicado o ausente en {rel}, se omite")
            continue
        if src.count(old) != 1:
            raise SystemExit(f"[FALLO] anclaje #{i} no es unico en {rel} ({src.count(old)} veces)")
        src = src.replace(old, new)
        print(f"[ok] {rel}: bloque #{i} aplicado")
    path.write_text(src, encoding="utf-8", newline="")


# ----------------------------------------------------------------------------
# 1) Backend: sync.py — /reassign con force_overquota
# ----------------------------------------------------------------------------
SYNC_REPLACEMENTS = [
    # 1.1 Validación de cupo
    (
        '    # Verificar cupo del nuevo coordinador\n'
        '    ok, msg, info = await _check_coordinator_quota(db, assignment.event_id, new_coordinator)\n'
        '    if not ok:\n'
        '        raise HTTPException(409, detail={"error": "QUOTA_FULL", "message": msg})\n',
        '    # Verificar cupo del nuevo coordinador. force_overquota permite la cesion\n'
        '    # aunque el cupo destino este lleno (misma semantica que en check-in:\n'
        '    # el cupo es informativo y nunca debe dejar al staff sin salida).\n'
        '    force = bool(payload.get("force_overquota", False))\n'
        '    overquota = False\n'
        '    ok, msg, info = await _check_coordinator_quota(db, assignment.event_id, new_coordinator)\n'
        '    if not ok:\n'
        '        if not force:\n'
        '            raise HTTPException(409, detail={"error": "QUOTA_FULL", "message": msg})\n'
        '        overquota = True\n'
        '        logger.info(\n'
        '            "Reasignacion en sobrecupo hacia %s en evento %s (%s)",\n'
        '            new_coordinator, assignment.event_id, msg,\n'
        '        )\n',
    ),
    # 1.2 Audit log con flag overquota
    (
        '                "new_coordinator": new_coordinator,\n'
        '                "reason": reason,\n'
        '            },\n',
        '                "new_coordinator": new_coordinator,\n'
        '                "reason": reason,\n'
        '                "overquota": overquota,\n'
        '            },\n',
    ),
    # 1.3 Respuesta con flag overquota (indent 8 espacios = return, no el dict del audit/ws)
    (
        '        "old_coordinator": old,\n'
        '        "new_coordinator": new_coordinator,\n',
        '        "old_coordinator": old,\n'
        '        "new_coordinator": new_coordinator,\n'
        '        "overquota": overquota,\n',
    ),
]

# ----------------------------------------------------------------------------
# 2) Frontend: checkin.html — escapes de sobrecupo en reasignación
# ----------------------------------------------------------------------------
CHECKIN_REPLACEMENTS = [
    # 2.1 Modal: botón "dejar en sobrecupo" (siempre visible, escape total)
    (
        "    if (!suggestions || !suggestions.length) {\n"
        "        list.innerHTML = '<p class=\"text-sm text-gray-500 text-center py-4\">No hay coordinadores con cupo disponible.</p>';\n"
        "    } else {\n"
        "        list.innerHTML = suggestions.map(s => `\n"
        "            <button onclick=\"confirmReassign('${s.coordinator}')\"\n"
        "                class=\"w-full text-left p-3 rounded-lg border hover:bg-amber-50 transition flex justify-between items-center\">\n"
        "                <span class=\"font-medium\">${s.coordinator}</span>\n"
        "                <span class=\"text-xs text-green-600\">${s.available} cupos</span>\n"
        "            </button>\n"
        "        `).join('');\n"
        "    }\n"
        "    modal.classList.remove('hidden');\n"
        "}\n",
        "    // Escape: dejar al operador en sobrecupo con su coordinador actual\n"
        "    // (cuando TODOS los coordinadores estan llenos no hay a quien ceder).\n"
        "    const forceBtn = `\n"
        "        <button onclick=\"forceOverquotaFromModal()\"\n"
        "            class=\"w-full text-left p-3 rounded-lg border border-amber-300 bg-amber-50 hover:bg-amber-100 transition text-sm font-medium text-amber-800 mt-2\">\n"
        "            ⚠️ Dejar en sobrecupo con ${coordinatorName || 'el coordinador actual'}\n"
        "        </button>`;\n"
        "    if (!suggestions || !suggestions.length) {\n"
        "        list.innerHTML = forceBtn + '<p class=\"text-sm text-gray-500 text-center py-4\">No hay coordinadores con cupo disponible.</p>';\n"
        "    } else {\n"
        "        list.innerHTML = suggestions.map(s => `\n"
        "            <button onclick=\"confirmReassign('${s.coordinator}')\"\n"
        "                class=\"w-full text-left p-3 rounded-lg border hover:bg-amber-50 transition flex justify-between items-center\">\n"
        "                <span class=\"font-medium\">${s.coordinator}</span>\n"
        "                <span class=\"text-xs text-green-600\">${s.available} cupos</span>\n"
        "            </button>\n"
        "        `).join('') + forceBtn;\n"
        "    }\n"
        "    modal.classList.remove('hidden');\n"
        "}\n"
        "\n"
        "// Escape del modal de cupo lleno: reintenta el check-in con force_overquota.\n"
        "async function forceOverquotaFromModal() {\n"
        "    document.getElementById('reassign-modal').classList.add('hidden');\n"
        "    _reassignAssignmentId = null;\n"
        "    _retryingOverquota = true;\n"
        "    try {\n"
        "        await doCheckIn();\n"
        "    } finally {\n"
        "        _retryingOverquota = false;\n"
        "    }\n"
        "}\n",
    ),
    # 2.2 confirmReassign: firma con force
    (
        "async function confirmReassign(newCoordinator) {\n",
        "async function confirmReassign(newCoordinator, force) {\n",
    ),
    # 2.3 confirmReassign: enviar flag
    (
        "            body: JSON.stringify({ new_coordinator: newCoordinator })\n",
        "            body: JSON.stringify({ new_coordinator: newCoordinator, force_overquota: !!force })\n",
    ),
    # 2.4 confirmReassign: 409 QUOTA_FULL -> ofrecer forzar
    (
        "        } else {\n"
        "            const err = await resp.json().catch(() => ({}));\n"
        "            const errMsg = (err.detail && err.detail.message) ? err.detail.message : (err.detail || 'desconocido');\n"
        "            alert('Error al reasignar: ' + errMsg);\n"
        "        }\n",
        "        } else {\n"
        "            const err = await resp.json().catch(() => ({}));\n"
        "            // QUOTA_FULL: ofrecer forzar la cesion aunque el destino este lleno\n"
        "            if (!force && err.detail && typeof err.detail === 'object' && err.detail.error === 'QUOTA_FULL') {\n"
        "                if (confirm(`El cupo de ${newCoordinator} está lleno.\\n\\n¿Forzar la cesión de todos modos (sobrecupo)?`)) {\n"
        "                    return confirmReassign(newCoordinator, true);\n"
        "                }\n"
        "            }\n"
        "            const errMsg = (err.detail && err.detail.message) ? err.detail.message : (err.detail || 'desconocido');\n"
        "            alert('Error al reasignar: ' + errMsg);\n"
        "        }\n",
    ),
    # 2.5 changeCoordinator: firma con force
    (
        "async function changeCoordinator() {\n",
        "async function changeCoordinator(force) {\n",
    ),
    # 2.6 changeCoordinator: enviar flag
    (
        "            body: JSON.stringify({\n"
        "                new_coordinator: newCoord,\n"
        "                reason: 'Cambio manual post-checkin'\n"
        "            })\n",
        "            body: JSON.stringify({\n"
        "                new_coordinator: newCoord,\n"
        "                reason: 'Cambio manual post-checkin',\n"
        "                force_overquota: !!force\n"
        "            })\n",
    ),
    # 2.7 changeCoordinator: 409 QUOTA_FULL -> ofrecer forzar
    (
        "        } else if (resp.status === 409) {\n"
        "            const errData = await resp.json().catch(() => ({}));\n"
        "            const msg = (errData.detail && errData.detail.message) || errData.detail || 'Cupo lleno';\n"
        "            alert('No se pudo reasignar: ' + msg);\n"
        "        } else {\n",
        "        } else if (resp.status === 409) {\n"
        "            const errData = await resp.json().catch(() => ({}));\n"
        "            const isQF = errData.detail && typeof errData.detail === 'object' && errData.detail.error === 'QUOTA_FULL';\n"
        "            // QUOTA_FULL: ofrecer forzar el cambio aunque el destino este lleno\n"
        "            if (!force && isQF && confirm(`El cupo de ${newCoord} está lleno.\\n\\n¿Forzar el cambio de todos modos (sobrecupo)?`)) {\n"
        "                return changeCoordinator(true);\n"
        "            }\n"
        "            const msg = (errData.detail && errData.detail.message) || errData.detail || 'Cupo lleno';\n"
        "            alert('No se pudo reasignar: ' + msg);\n"
        "        } else {\n",
    ),
]

# ----------------------------------------------------------------------------
# 3) Tests: test_checkin_overquota.py — caso reassign
# ----------------------------------------------------------------------------
NEW_TEST = '''

@pytest.mark.asyncio
async def test_reassign_force_overquota(client, overquota_env, db: AsyncSession):
    """Regression: /reassign con force_overquota permite ceder a un coordinador lleno.

    Sin force: 409 QUOTA_FULL. Con force: 200 y flag overquota en respuesta
    (antes no habia salida cuando TODOS los coordinadores estaban llenos).
    """
    env = overquota_env
    a1 = env["assignment_checked"]
    # Mover a1 a PEDRO para que XIMENA quede llena justo (a3 = 1/1)
    a1.admitted_by = "PEDRO"
    await db.commit()
    headers = {"Authorization": f"Bearer {env['token']}"}

    # Sin force: rechazado con QUOTA_FULL
    resp = await client.patch(
        f"/api/sync/assignments/{a1.id}/reassign",
        headers=headers,
        json={"new_coordinator": "XIMENA"},
    )
    assert resp.status_code == 409, resp.text
    assert resp.json()["detail"]["error"] == "QUOTA_FULL"

    # Con force: permitido en sobrecupo
    resp2 = await client.patch(
        f"/api/sync/assignments/{a1.id}/reassign",
        headers=headers,
        json={"new_coordinator": "XIMENA", "force_overquota": True},
    )
    assert resp2.status_code == 200, resp2.text
    data = resp2.json()
    assert data["overquota"] is True
    assert data["old_coordinator"] == "PEDRO"
    assert data["new_coordinator"] == "XIMENA"
'''


def main() -> int:
    patch_file("app/routers/sync.py", SYNC_REPLACEMENTS, must_apply=[0, 1, 2])
    patch_file("app/templates/admin/checkin.html", CHECKIN_REPLACEMENTS, must_apply=[0, 1, 2, 3, 4, 5, 6])

    tests_path = BACKEND / "tests" / "test_checkin_overquota.py"
    tests_src = tests_path.read_text(encoding="utf-8")
    marker = "async def test_reassign_force_overquota"
    if marker not in tests_src:
        with io.open(tests_path, "a", encoding="utf-8", newline="") as fh:
            fh.write(NEW_TEST)
        print("[ok] tests/test_checkin_overquota.py: test agregado")
    else:
        print("[aviso] test ya presente, se omite")
    print("Parche completado.")
    return 0


if __name__ == "__main__":
    sys.exit(main())