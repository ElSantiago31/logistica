"""Parche: actualiza las instrucciones del modal de importacion en
event_detail.html para documentar la columna ETAPA (dropdown en plantilla).
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "app" / "templates" / "admin" / "event_detail.html"

src = TARGET.read_text(encoding="utf-8")
orig = src

anchor = (
    "                        <li>El nombre del coordinador debe coincidir con los cupos asignados al evento.</li>\n"
)
new_li = (
    "                        <li>El nombre del coordinador debe coincidir con los cupos asignados al evento.</li>\n"
    "                        <li>La columna <strong>ETAPA</strong> (previa, avanzada, evento, desmontaje) define la etapa de la asignaci\u00f3n; vac\u00eda = evento. La misma persona puede ir en varias etapas (doble turno).</li>\n"
)

if "La columna <strong>ETAPA</strong>" in src:
    print("Ya aplicado; sin cambios.")
else:
    if anchor not in src:
        raise SystemExit("ERROR: ancla de instrucciones no encontrada")
    src = src.replace(anchor, new_li, 1)
    TARGET.write_text(src, encoding="utf-8")
    print("OK: instruccion ETAPA agregada al modal de import")

# Verificacion
chk = TARGET.read_text(encoding="utf-8")
assert "La columna <strong>ETAPA</strong>" in chk, "FALLO la verificacion"
print("VERIFICADO: modal documenta la columna ETAPA")