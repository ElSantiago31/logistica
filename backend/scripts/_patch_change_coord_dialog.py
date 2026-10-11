# -*- coding: utf-8 -*-
"""Corrige el doble diálogo al cambiar coordinador con sobrecupo.

Antes: el reintento llamaba changeCoordinator(true), que re-ejecutaba toda
la función y el confirm "¿Cambiar el coordinador...?" salía 2 veces.
Ahora: el reintento usa la bandera _coordForce para saltar el confirm
inicial y solo reenvía el PATCH con force_overquota=true.
"""
import io

P = r"app\templates\admin\checkin.html"

OLD_HEAD = "async function changeCoordinator(force) {"
NEW_HEAD = (
    "// _coordForce=true -> reintento de sobrecupo: omite el confirm inicial y\n"
    "// solo reenvia el PATCH con force_overquota (antes el dialogo salia 2 veces).\n"
    "let _coordForce = false;\n"
    "async function changeCoordinator() {\n"
    "    const force = _coordForce;\n"
    "    _coordForce = false;"
)

OLD_CONFIRM = (
    '    if (!confirm(`¿Cambiar el coordinador de "${currentOperator.full_name}"?\\n\\n` +\n'
    "        `De: ${currentCoord || '(sin asignar)'}\\nA: ${newCoord}`)) return;"
)
NEW_CONFIRM = (
    '    if (!force && !confirm(`¿Cambiar el coordinador de "${currentOperator.full_name}"?\\n\\n` +\n'
    "        `De: ${currentCoord || '(sin asignar)'}\\nA: ${newCoord}`)) return;"
)

OLD_RETRY = (
    "            if (!force && isQF && confirm(`El cupo de ${newCoord} está lleno.\\n\\n¿Forzar el cambio de todos modos (sobrecupo)?`)) {\n"
    "                return changeCoordinator(true);\n"
    "            }"
)
NEW_RETRY = (
    "            if (!force && isQF && confirm(`El cupo de ${newCoord} está lleno.\\n\\n¿Forzar el cambio de todos modos (sobrecupo)?`)) {\n"
    "                _coordForce = true;   // reintenta SOLO el PATCH, sin repetir el confirm inicial\n"
    "                return changeCoordinator();\n"
    "            }"
)


def main():
    s = io.open(P, encoding="utf-8").read()

    if "_coordForce" in s:
        print("Ya parcheado — sin cambios.")
        return

    n = s.count(OLD_HEAD)
    assert n == 1, "OLD_HEAD encontrada %d veces" % n
    s = s.replace(OLD_HEAD, NEW_HEAD)

    n = s.count(OLD_CONFIRM)
    assert n == 1, "OLD_CONFIRM encontrada %d veces" % n
    s = s.replace(OLD_CONFIRM, NEW_CONFIRM)

    n = s.count(OLD_RETRY)
    assert n == 1, "OLD_RETRY encontrada %d veces" % n
    s = s.replace(OLD_RETRY, NEW_RETRY)

    io.open(P, "w", encoding="utf-8", newline="").write(s)
    print("PATCH OK")


if __name__ == "__main__":
    main()