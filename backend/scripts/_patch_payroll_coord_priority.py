# -*- coding: utf-8 -*-
"""Parche: coordinador VIGENTE en nómina/planilla (admitted_by > programmed_by).

Bug: la Incorporación Rápida (quick_add) fija programmed_by="Colab A&C"
(histórico del registro web) y el botón "Cambiar Coordinador" del check-in
actualiza SOLO admitted_by. Como la planilla priorizaba programmed_by,
imprimía siempre "Colab A&C" aunque el coordinador hubiera cambiado.

Fix (ya aplicado en payroll.py): coord_name = admitted_by or programmed_by.
Este parche:
  1. Actualiza los comentarios obsoletos de payroll.py.
  2. Agrega test de regresión en tests/test_payroll.py.

Uso:  python scripts/_patch_payroll_coord_priority.py  (desde backend/)
"""
import io
import os

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def patch(path, replacements):
    full = os.path.join(BASE, path)
    with io.open(full, encoding="utf-8") as f:
        src = f.read()
    changed = False
    for old, new in replacements:
        n = src.count(old)
        if n == 0:
            print("[skip] ya aplicado o no encontrado: %s" % old[:60])
            continue
        src = src.replace(old, new)
        changed = True
        print("[%s] reemplazado x%d" % (path, n))
    with io.open(full, "w", encoding="utf-8", newline="") as f:
        f.write(src)


# ---------------------------------------------------------------------------
# 1) payroll.py: comentarios obsoletos (la prioridad ya se invirtió a mano)
# ---------------------------------------------------------------------------
patch(
    os.path.join("app", "routers", "payroll.py"),
    [
        (
            "# [NÓMINA-V2] Determinar coordinador: quien lo programó (programmed_by)\n"
            "        # tiene prioridad. Fallback: admitted_by → mapping por área → \"Sin asignar\".",
            "# [NÓMINA-V2] Coordinador VIGENTE: admitted_by (quien lo admite en\n"
            "        # check-in; lo actualiza \"Cambiar Coordinador\") tiene prioridad.\n"
            "        # Fallback: programmed_by (histórico) → mapping por área → \"Sin asignar\".",
        ),
        (
            "# Determinar coordinador: quien lo programó (programmed_by) tiene\n"
            "        # prioridad. Fallback: admitted_by → mapping por área → \"Sin asignar\".",
            "# Coordinador VIGENTE: admitted_by (actualizado por check-in y por\n"
            "        # \"Cambiar Coordinador\") tiene prioridad sobre el histórico\n"
            "        # programmed_by (p. ej. \"Colab A&C\" de la Incorporación Rápida).\n"
            "        # Fallback: mapping por área → \"Sin asignar\".",
        ),
    ],
)

# ---------------------------------------------------------------------------
# 2) test_payroll.py: fixture con programmed_by histórico + test de regresión
# ---------------------------------------------------------------------------
TEST_PATH = os.path.join("tests", "test_payroll.py")

# 2a. Fixture: asignaciones checked_in con programmed_by="Colab A&C"
#     (histórico del registro web) y admitted_by="Carlos Coordinador"
#     (coordinador vigente tras el check-in / reassign).
patch(
    TEST_PATH,
    [
        (
            "assign_coord = EventAssignment(\n"
            "        event_id=event.id,\n"
            "        operator_id=op_coord_profile.id,\n"
            "        role_id=role_coord.id,\n"
            "        status=\"checked_in\"\n"
            "    )",
            "assign_coord = EventAssignment(\n"
            "        event_id=event.id,\n"
            "        operator_id=op_coord_profile.id,\n"
            "        role_id=role_coord.id,\n"
            "        status=\"checked_in\",\n"
            "        programmed_by=\"Colab A&C\",\n"
            "        admitted_by=\"Carlos Coordinador\"\n"
            "    )",
        ),
        (
            "assign_op1 = EventAssignment(\n"
            "        event_id=event.id,\n"
            "        operator_id=op_profile1.id,\n"
            "        role_id=role_operator.id,\n"
            "        status=\"checked_in\",\n"
            "        jacket_number=\"J-10\",\n"
            "        cap_number=\"C-05\"\n"
            "    )",
            "assign_op1 = EventAssignment(\n"
            "        event_id=event.id,\n"
            "        operator_id=op_profile1.id,\n"
            "        role_id=role_operator.id,\n"
            "        status=\"checked_in\",\n"
            "        jacket_number=\"J-10\",\n"
            "        cap_number=\"C-05\",\n"
            "        programmed_by=\"Colab A&C\",\n"
            "        admitted_by=\"Carlos Coordinador\"\n"
            "    )",
        ),
    ],
)

# 2b. Test de regresión: la planilla debe agrupar por el coordinador VIGENTE
REGRESSION_TEST = '''

@pytest.mark.asyncio
async def test_planilla_uses_admitted_by_over_programmed_by(
    client: AsyncClient, admin_token: str, setup_payroll_event
):
    """Regresión: la planilla debe agrupar por el coordinador VIGENTE.

    Escenario real del bug: operadores registrados con la Incorporación
    Rápida traen programmed_by="Colab A&C" (histórico del registro web) y el
    check-in / "Cambiar Coordinador" fija admitted_by="Carlos Coordinador".
    La planilla debe usar admitted_by (vigente), no programmed_by.
    """
    event, _ = setup_payroll_event
    response = await client.get(
        f"/api/payroll/events/{event.id}/planilla-coordinador",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert response.status_code == 200
    wb = openpyxl.load_workbook(BytesIO(response.content))

    # La hoja debe llamarse como el coordinador VIGENTE (admitted_by),
    # NO como el histórico programmed_by="Colab A&C".
    assert "Carlos Coordinador" in wb.sheetnames
    assert "Colab A&C" not in wb.sheetnames
'''

with io.open(os.path.join(BASE, TEST_PATH), encoding="utf-8") as f:
    src = f.read()

if "test_planilla_uses_admitted_by_over_programmed_by" not in src:
    with io.open(os.path.join(BASE, TEST_PATH), "w", encoding="utf-8", newline="") as f:
        f.write(src.rstrip("\n") + "\n" + REGRESSION_TEST)
    print("[tests/test_payroll.py] test de regresión agregado")
else:
    print("[tests/test_payroll.py] test de regresión ya existía (skip)")

print("Parche completado OK")