"""Servicio para generar el Excel de planilla de pago.

Toma la plantilla ``Planilla_Logistica_Eventos.xlsx`` (con logo, formato y
encabezado) y genera un workbook con:

- ``group_by="coordinator"`` (default): una hoja por cada coordinador.
- ``group_by="none"``: una hoja plana (lista única) titulada con el evento.

Dentro de cada hoja, los operadores se ordenan por:

- ``sort_by="lastname"`` (default): por apellido (alfabético).
- ``sort_by="document"``: por número de cédula (numérico cuando es posible).

Si una hoja tiene más de 20 operadores, se generan hojas adicionales
paginadas (``COORDINADOR (1)``, ``COORDINADOR (2)``, ... o
``EVENTO (1)``, ``EVENTO (2)`` ...).

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
import re
import copy as _copy
import logging
import unicodedata
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


def _sort_key_by_lastname(full_name: str) -> tuple[str, str]:
    """Clave de ordenamiento por APELLIDO (case-insensitive, sin acentos).

    Usa la MISMA lógica que ``_split_name`` para extraer el apellido:
    todo después del primer token se considera apellido.

    Ej: "JUAN CARLOS PEREZ GOMEZ" → clave ("PEREZ GOMEZ", "JUAN CARLOS")

    Operadores sin apellido (un solo token) se ordenan por ese token como
    apellido.

    Returns:
        Tuple (apellido_norm, nombre_norm) para usar en ``sorted(key=...)``.
    """
    nombres, apellidos = _split_name(full_name)

    def _norm(text: str) -> str:
        """Normaliza: quita acentos y pasa a mayúsculas para orden estable."""
        if not text:
            return ""
        nfkd = unicodedata.normalize("NFKD", text)
        return nfkd.encode("ascii", "ignore").decode("ascii").upper().strip()

    # Si no hay apellido (un solo token), usar el nombre como apellido
    # para que se ubique alfabéticamente en lugar de quedar agrupado al final.
    return (_norm(apellidos) or _norm(nombres), _norm(nombres))


def _sort_key_by_document(op: dict) -> tuple:
    """Clave de ordenamiento por número de cédula (numérico cuando es posible).

    Extrae la parte numérica inicial del ``document_number`` para ordenar
    correctamente (``"1020"`` < ``"52000"``). Si no es numérico, ordena como
    string al final de la lista numérica.

    Returns:
        Tuple ``(is_numeric, numeric_value, raw)`` para usar en ``sorted``.
    """
    raw = (op.get("document_number") or "").strip()
    if not raw:
        return (False, 0, "")
    # Extraer dígitos iniciales
    m = re.match(r"^(\d+)", raw)
    if m:
        return (True, int(m.group(1)), raw)
    return (False, 0, raw.upper())


# Caracteres prohibidos en nombres de hojas de Excel
_SHEET_INVALID_CHARS = re.compile(r"[\[\]\*\/\\\?\:]")


def _sanitize_sheet_title(title: str, page_num: int | None = None) -> str:
    """Sanea un título para usarlo como nombre de hoja Excel.

    - Elimina caracteres prohibidos: ``[ ] * / \\ ? :``
    - Recorta a 31 caracteres (límite de Excel)
    - Si ``page_num`` no es None, añade `` (N)`` reservando espacio
    """
    cleaned = _SHEET_INVALID_CHARS.sub(" ", title or "").strip()
    if page_num is not None:
        suffix = f" ({page_num})"
        # Reservar espacio para el sufijo
        max_len = 31 - len(suffix)
        cleaned = cleaned[:max_len] + suffix
    else:
        cleaned = cleaned[:31]
    return cleaned or "Hoja"


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


def _sort_operators(operators: list[dict], sort_by: str) -> list[dict]:
    """Ordena una lista de operadores según el criterio indicado.

    Args:
        operators: Lista de dicts de operadores.
        sort_by: ``"lastname"`` (default) o ``"document"``.

    Returns:
        Nueva lista ordenada (no muta la original).
    """
    if sort_by == "document":
        return sorted(operators, key=_sort_key_by_document)
    # default: lastname
    return sorted(
        operators,
        key=lambda op: _sort_key_by_lastname(op.get("full_name", "")),
    )


def _render_pages(
    *,
    template_wb: openpyxl.Workbook,
    template_ws,
    event_name: str,
    event_date: datetime | None,
    event_location: str,
    sheet_label: str,
    operators: list[dict],
    sort_by: str = "lastname",
) -> list[str]:
    """Crea una o varias hojas (paginadas cada ROWS_PER_PAGE) para un grupo.

    Args:
        sheet_label: Nombre base para las hojas (p.ej. nombre del coordinador
            o el nombre del evento cuando ``group_by="none"``).
        operators: Operadores del grupo (se ordenan aquí según ``sort_by``).

    Returns:
        Lista con los títulos de las hojas creadas.
    """
    operators = _sort_operators(list(operators), sort_by)
    sheets_created = []
    total_pages = max(1, (len(operators) + ROWS_PER_PAGE - 1) // ROWS_PER_PAGE)

    for page_num in range(total_pages):
        start = page_num * ROWS_PER_PAGE
        end = start + ROWS_PER_PAGE
        page_ops = operators[start:end]

        # Título de la hoja (con sufijo de página si hay más de una)
        page_suffix = page_num + 1 if total_pages > 1 else None
        sheet_title = _sanitize_sheet_title(sheet_label, page_num=page_suffix)

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

    return sheets_created


def generate_planilla_xlsx(
    *,
    event_name: str,
    event_date: datetime | None,
    event_location: str,
    operators_by_coordinator: dict[str, list[dict]] | None = None,
    operators: list[dict] | None = None,
    group_by: str = "coordinator",
    sort_by: str = "lastname",
) -> bytes:
    """Genera el Excel de la planilla de pago.

    Modos soportados (combinaciones de ``group_by`` y ``sort_by``):

    ================== ============= =============
    group_by           sort_by       Descripción
    ================== ============= =============
    ``"coordinator"``  ``"lastname"``  Hoja por coordinador, ordenado por apellido (default)
    ``"coordinator"``  ``"document"``  Hoja por coordinador, ordenado por cédula
    ``"none"``         ``"lastname"``  Lista única, ordenada por apellido
    ``"none"``         ``"document"``  Lista única, ordenada por cédula
    ================== ============= =============

    Args:
        event_name: Nombre del evento.
        event_date: Fecha/hora de inicio del evento.
        event_location: Lugar del evento.
        operators_by_coordinator: (Retrocompatibilidad) Dict
            {coordinator_name: [op_data, ...]}. Si se pasa, se usa como
            fuente de datos (ignora ``operators`` y ``group_by`` queda
            forzado a ``"coordinator"``).
        operators: Lista plana de op_data. Necesario cuando
            ``group_by="none"``. Cada op_data tiene las claves:
            full_name, document_number, address, phone,
            coordinator_name, jacket_number, cap_number.
        group_by: ``"coordinator"`` o ``"none"``.
        sort_by: ``"lastname"`` o ``"document"``.

    Returns:
        bytes con el contenido del archivo .xlsx listo para devolver como
        StreamingResponse.
    """
    if not TEMPLATE_PATH.exists():
        raise FileNotFoundError(f"Plantilla no encontrada: {TEMPLATE_PATH}")

    # Cargar plantilla
    template_wb = openpyxl.load_workbook(TEMPLATE_PATH)
    template_ws = template_wb[TEMPLATE_SHEET]

    # --- Retrocompatibilidad: si llega operators_by_coordinator, usarlo ---
    if operators_by_coordinator is not None:
        operators = []
        for coord_name, ops in operators_by_coordinator.items():
            for op in ops:
                # Asegurar que cada op lleve su coordinator_name
                op_copy = dict(op)
                op_copy.setdefault("coordinator_name", coord_name)
                operators.append(op_copy)
        group_by = "coordinator"

    # Caso edge: sin operadores → devolver plantilla con datos del evento
    if not operators:
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

    sheets_created: list[str] = []

    if group_by == "coordinator":
        # Agrupar operadores por coordinator_name (preservando el orden
        # de aparición para títulos estables).
        groups: dict[str, list[dict]] = {}
        for op in operators:
            coord_name = op.get("coordinator_name") or "SIN COORDINADOR"
            groups.setdefault(coord_name, []).append(op)

        for coord_name, ops in groups.items():
            sheets_created.extend(
                _render_pages(
                    template_wb=template_wb,
                    template_ws=template_ws,
                    event_name=event_name,
                    event_date=event_date,
                    event_location=event_location,
                    sheet_label=coord_name,
                    operators=ops,
                    sort_by=sort_by,
                )
            )
    else:
        # group_by == "none": lista única titulada con el nombre del evento
        sheets_created.extend(
            _render_pages(
                template_wb=template_wb,
                template_ws=template_ws,
                event_name=event_name,
                event_date=event_date,
                event_location=event_location,
                sheet_label=event_name or "EVENTO",
                operators=operators,
                sort_by=sort_by,
            )
        )

    # Eliminar la hoja plantilla original (si ya creamos al menos una)
    if sheets_created:
        del template_wb[TEMPLATE_SHEET]
        # La primera hoja queda como activa
        template_wb.active = 0

    # Serializar a bytes
    buf = io.BytesIO()
    template_wb.save(buf)
    logger.info(
        "Planilla generada: evento=%r, group_by=%s, sort_by=%s, hojas=%s",
        event_name,
        group_by,
        sort_by,
        sheets_created,
    )
    return buf.getvalue()
