"""Parche one-off: en checkin.html la etapa 'avanzada' debe mostrarse como
'Avanzada' (no 'Montaje avanzada') en el filtro de etapas y en las
etiquetas derivadas (STAGE_LABELS: filtro activo, tag de lista y detalle).
"""
import io

PATH = r"backend/app/templates/admin/checkin.html"

REPLACEMENTS = [
    (
        '<option value="avanzada">Montaje avanzada</option>',
        '<option value="avanzada">Avanzada</option>',
    ),
    (
        "const STAGE_LABELS = { previa: 'Previa', avanzada: 'Montaje avanzada', evento: 'Evento', desmontaje: 'Desmontaje' };",
        "const STAGE_LABELS = { previa: 'Previa', avanzada: 'Avanzada', evento: 'Evento', desmontaje: 'Desmontaje' };",
    ),
]


def main():
    s = io.open(PATH, encoding="utf-8").read()
    if "Montaje avanzada" not in s:
        print("YA APLICADO (sin rastro del texto)")
        return
    for old, new in REPLACEMENTS:
        if old not in s:
            raise SystemExit("ERROR: bloque SEARCH no encontrado:\n" + old[:120])
        s = s.replace(old, new, 1)
    io.open(PATH, "w", encoding="utf-8", newline="").write(s)
    ok = "Montaje avanzada" not in io.open(PATH, encoding="utf-8").read()
    print("APLICADO" if ok else "FALLO VERIFICACION")


if __name__ == "__main__":
    main()