"""Servicio para generar el Excel de planilla de pago por coordinador.

Toma la plantilla ``Planilla_Logistica_Eventos.xlsx`` (con logo, formato y
encabezado) y genera un workbook con una hoja por cada coordinador del evento.
Si un coordinador tiene más de 20 operadores, se generan hojas adicionales
paginadas (``COORDINADOR (1)``, ``COORDINADOR (2)``, ...).

Solo se incluyen los operadores con ``status='checked_in'``.

Estructura de la plantilla (1 hoja "Planilla"):
    Encabezado:
        D5  → COORDINADOR GENERAL  (celda combinada D5:J5)
        D6  → NOMBRE DEL EVENTO    (celda combinada D6:G6)
        D7  → FECHA                (celda combinada D7:H7)
        K7  → LUGAR                (celda combinada K7:M7)
    Tabla (filas 9-28, 20 operadores pre-numerados):
        B=No | C=NOMBRES | D=APELLIDOS | E=CEDULA | F=DIRECCION
        G=CELULAR | H=COORDINADOR | I=No CHAQ | J=No GORRA
        K=VALOR | L=FIRMA | M=No DSE   (estos quedan vacíos)
"""
import io
import copy as _copy
import logging
from pathlib import Path
from datetime import datetime

import openpyxl

logger = logging.getLogger(__name__)

# --- Configuración de la plantilla ---
TEMPLATE_PATH = (
    Path(__file__).resolve().parent.parent
    / "templates"
    / "Planilla_Logistica_Eventos.xlsx"
)
TEMPLATE_SHEET = "Planilla"
ROWS_PER_PAGE = 20
FIRST_DATA_ROW = 9  # primera fila de datos en la plantilla
LAST_DATA_ROW = FIRST_DATA_ROW + ROWS_PER_PAGE - 1  # 28

# --- Columnas (1-indexed) según el header de la plantilla ---
COL_NO = 2           # B  — No (viene pre-numerado en la plantilla)
COL_NOMBRES = 3      # C
COL_APELLIDOS = 4    # D
COL_CEDULA = 5       # E
COL_DIRECCION = 6    # F
COL_CELULAR = 7      # G
COL_COORDINADOR = 8  # H
COL_CHAQ = 9         # I
COL_GORRA = 10       # J
# K=VALOR, L=FIRMA, M=No DSE → se dejan vacíos (no tenemos el dato)

# --- Celdas del encabezado (top-left de la celda combinada) ---
CELL_COORD = "D5"
CELL_EVENTO = "D6"
CELL_FECHA = "D7"
CELL_LUGAR = "K7"


def _split_name(full_name: str) -> tuple[str, str]:
    """Divide un nombre completo en (nombres, apellidos).

    El primer token se considera nombre y el resto apellidos.
    Ej: "JUAN CARLOS PEREZ GOMEZ" → ("JUAN CARLOS", "PEREZ GOMEZ")
    Pero el usuario pidió: primer token = nombre, resto = apellidos.
    """
    if not full_name:
        return ("", "")
    parts = full_name.strip().split(None, 1)
    if len(parts) == 1:
        return (parts[0], "")
    return (parts[0], parts[1])


def _fmt_date(dt: datetime | None) -> str:
    """Formatea una fecha como DD/MM/YYYY para la planilla."""
    if not dt:
        return ""
    # Si tiene tzinfo, convertir a Bogotá
    try:
        from app.routers.payroll import BOGOTA_TZ
        if dt.tzinfo is not None:
            dt = dt.astimezone(BOGOTA_TZ)
    except Exception:
        pass
    return dt.strftime("%d/%m/%Y")


def _copy_sheet_with_images(wb: openpyxl.Workbook, src_sheet: openpyxl.worksheet.worksheet.Worksheet, new_title: str):
    """Copia una hoja dentro del workbook preservando imágenes (logo).

    ``openpyxl.Workbook.copy_worksheet`` NO copia imágenes, así que las
    re-agregamos manualmente tras la copia.

    Nota: Se usa ``deepcopy`` en vez de ``copy`` para evitar que múltiples
    hojas compartan el mismo ``BytesIO`` de la imagen, lo cual causa
    ``ValueError: I/O operation on closed file`` al serializar.
    """
    new_ws = wb.copy_worksheet(src_sheet)
    new_ws.title = new_title

    # Re-agregar imágenes (logo) — copy_worksheet no las copia
    if src_sheet._images:
        for img in src_sheet._images:
            new_img = _copy.deepcopy(img)
            new_ws._images.append(new_img)

    return new_ws


def _fill_header(ws, *, coordinator: str, event_name: str, event_date, event_location: str):
    """Rellena las celdas del encabezado de una hoja."""
    ws[CELL_COORD] = coordinator or ""
    ws[CELL_EVENTO] = event_name or ""
    ws[CELL_FECHA] = _fmt_date(event_date)
    ws[CELL_LUGAR] = event_location or ""


def _fill_operators(ws, operators: list[dict]):
    """Rellena las filas de operadores (a partir de la fila 9).

    ``operators`` es una lista de dicts con las claves:
        full_name, document_number, address, phone,
        coordinator_name, jacket_number, cap_number
    """
    for idx, op in enumerate(operators):
        row = FIRST_DATA_ROW + idx
        if row > LAST_DATA_ROW:
            break  # seguridad — el paginado ya fragmentó en bloques de 20
        nombres, apellidos = _split_name(op.get("full_name", ""))
        ws.cell(row=row, column=COL_NOMBRES, value=nombres)
        ws.cell(row=row, column=COL_APELLIDOS, value=apellidos)
        ws.cell(row=row, column=COL_CEDULA, value=op.get("document_number", ""))
        ws.cell(row=row, column=COL_DIRECCION, value=op.get("address", ""))
        ws.cell(row=row, column=COL_CELULAR, value=op.get("phone", ""))
        ws.cell(row=row, column=COL_COORDINADOR, value=op.get("coordinator_name", ""))
        ws.cell(row=row, column=COL_CHAQ, value=op.get("jacket_number", ""))
        ws.cell(row=row, column=COL_GORRA, value=op.get("cap_number", ""))


def generate_planilla_xlsx(
    *,
    event_name: str,
    event_date: datetime | None,
    event_location: str,
    operators_by_coordinator: dict[str, list[dict]],
) -> bytes:
    """Genera el Excel de la planilla de pago.

    Args:
        event_name: Nombre del evento.
        event_date: Fecha/hora de inicio del evento.
        event_location: Lugar del evento.
        operators_by_coordinator: Dict {coordinator_name: [op_data, ...]}
            donde cada op_data tiene las claves:
            full_name, document_number, address, phone,
            coordinator_name, jacket_number, cap_number

    Returns:
        bytes con el contenido del archivo .xlsx listo para devolver como
        StreamingResponse.
    """
    if not TEMPLATE_PATH.exists():
        raise FileNotFoundError(f"Plantilla no encontrada: {TEMPLATE_PATH}")

    # Cargar plantilla (keep_links=False para evitar problemas)
    template_wb = openpyxl.load_workbook(TEMPLATE_PATH)
    template_ws = template_wb[TEMPLATE_SHEET]

    # Caso edge: no hay coordinadores → devolver plantilla con datos del evento
    if not operators_by_coordinator:
        _fill_header(
            template_ws,
            coordinator="SIN COORDINADOR ASIGNADO",
            event_name=event_name,
            event_date=event_date,
            event_location=event_location,
        )
        buf = io.BytesIO()
        template_wb.save(buf)
        return buf.getvalue()

    # Crear una hoja por cada (coordinador + página de 20 operadores)
    sheets_created = []
    for coord_name, operators in operators_by_coordinator.items():
        # Paginar en bloques de ROWS_PER_PAGE
        total_pages = max(1, (len(operators) + ROWS_PER_PAGE - 1) // ROWS_PER_PAGE)
        for page_num in range(total_pages):
            start = page_num * ROWS_PER_PAGE
            end = start + ROWS_PER_PAGE
            page_ops = operators[start:end]

            # Título de la hoja
            if total_pages > 1:
                sheet_title = f"{coord_name} ({page_num + 1})"[:31]
            else:
                sheet_title = coord_name[:31]

            new_ws = _copy_sheet_with_images(template_wb, template_ws, sheet_title)
            _fill_header(
                new_ws,
                coordinator="",  # "Coordinador General" (D5) se deja vacío
                event_name=event_name,
                event_date=event_date,
                event_location=event_location,
            )
            _fill_operators(new_ws, page_ops)
            sheets_created.append(sheet_title)

    # Eliminar la hoja plantilla original (si ya creamos al menos una)
    if sheets_created:
        del template_wb[TEMPLATE_SHEET]
        # La primera hoja queda como activa
        template_wb.active = 0

    # Serializar a bytes
    buf = io.BytesIO()
    template_wb.save(buf)
    logger.info(
        "Planilla generada: evento=%r, coordinadores=%d, hojas=%s",
        event_name,
        len(operators_by_coordinator),
        sheets_created,
    )
    return buf.getvalue()