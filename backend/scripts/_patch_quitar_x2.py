"""Parche one-off: quitar el texto 'X2 DOBLE TURNO' de la columna VALOR
de la planilla Excel. La doble jornada vuelve a indicarse SOLO con la
casilla marcada (relleno azul DOUBLE_FILL en toda la fila), como antes.
La celda VALOR muestra únicamente el valor del turno.
"""
import io

PATH = r"backend/app/services/planilla_excel.py"

REPLACEMENTS = [
    # Comentario de definición de columna
    (
        'COL_VALOR = 12       # L - texto "X2 DOBLE TURNO" (doble turno)',
        'COL_VALOR = 12       # L - valor del turno (doble turno se marca con relleno azul)',
    ),
    # Bloque de escritura de la celda VALOR
    (
        """        # --- Columna L (VALOR): tarifa de ESTE turno + marca de doble turno ---
        # Cada fila de la planilla = un turno (una asignación). "rate" es lo
        # que se paga por ese turno (rate_applied de la asignación o
        # rate_per_shift del rol, definido al crear el evento, ej. $100.000).
        # El operador con doble turno aparece en 2 filas: ambas llevan la
        # marca X2 DOBLE TURNO + el valor de ese turno (cobra 2 pagos).
        _rate = op.get("rate")
        _valor = f"${_rate:,.0f}".replace(",", ".") if _rate else ""
        if op.get("double_shift"):
            _valor_cell = ws.cell(
                row=row, column=COL_VALOR,
                value=f"X2 DOBLE TURNO {_valor}".strip(),
            )
            _valor_cell.font = Font(bold=True, color="1D4ED8")
        elif _valor:
            ws.cell(row=row, column=COL_VALOR, value=_valor)""",
        """        # --- Columna L (VALOR): tarifa de ESTE turno ---
        # Cada fila de la planilla = un turno (una asignación). "rate" es lo
        # que se paga por ese turno (rate_applied de la asignación o
        # rate_per_shift del rol, definido al crear el evento, ej. $100.000).
        # El operador con doble turno aparece en 2 filas (cobra 2 pagos):
        # la doble jornada se indica SOLO con la casilla marcada (fila
        # pintada de azul, DOUBLE_FILL), sin texto adicional.
        _rate = op.get("rate")
        _valor = f"${_rate:,.0f}".replace(",", ".") if _rate else ""
        if _valor:
            ws.cell(row=row, column=COL_VALOR, value=_valor)""",
    ),
]


def main():
    s = io.open(PATH, encoding="utf-8").read()
    if "X2 DOBLE TURNO" not in s:
        print("YA APLICADO (sin rastro del texto)")
        return
    for old, new in REPLACEMENTS:
        if old not in s:
            raise SystemExit("ERROR: bloque SEARCH no encontrado:\n" + old[:120])
        s = s.replace(old, new, 1)
    io.open(PATH, "w", encoding="utf-8", newline="").write(s)
    ok = "X2 DOBLE TURNO" not in io.open(PATH, encoding="utf-8").read()
    print("APLICADO" if ok else "FALLO VERIFICACION")


if __name__ == "__main__":
    main()