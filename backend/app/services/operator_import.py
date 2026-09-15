"""Importación masiva de operadores a un evento desde Excel (.xlsx).

Servicio principal que:
  1. Lee un Excel con 16 columnas oficiales.
  2. Crea usuarios (user_type=operator) + perfil Operator para los nuevos.
  3. Asigna (nuevos y existentes) al evento con status='confirmed'.
  4. Resuelve el coordinador contra EventCoordinatorQuota del evento.
  5. Devuelve un ImportSummary con métricas y detalle fila por fila.

Decisiones del producto:
  - Estado de asignación: 'confirmed'.
  - Contraseña: NumeroDocumento + TipoDocumento (ej: 1027522598CC), sin acentos.
  - Email auto-generado: {documento}@operador.temp.
  - Coordinador: se resuelve por nombre contra cupos del evento; fallback texto libre.
  - Manejo tolerante: una fila con error NO detiene el resto.
  - Re-importación: un operador ya asignado al evento se ACTUALIZA (cargo
    del evento, datos de perfil y coordinador). Un campo vacío del Excel
    NUNCA borra un valor existente (semántica COALESCE).
  - Pre-carga batch de catálogos (evita N+1).
  - Commit único al final.
"""
import asyncio
import io
import re
import time
import unicodedata
import uuid
from datetime import datetime, timezone
from typing import Optional

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Font, PatternFill, Alignment
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.events import DEFAULT_STAGE, EVENT_STAGES
from app.schemas.events import ImportRowResult, ImportSummary
from app.services.auth import hash_password
from app.services.referrals import get_referrer_operator_of


# ──────────────────────────────────────────────
#  Definición de columnas del Excel
# ──────────────────────────────────────────────

class ExcelColumn(dict):
    """Dict tipado para una columna del Excel."""
    pass


# Mapeo de columnas del Excel a claves internas.
# Los encabezados se comparan en UPPER + sin acentos para matching flexible.
EXPECTED_COLUMNS = [
    {"key": "primer_nombre",      "label": "PRIMER NOMBRE"},
    {"key": "segundo_nombre",     "label": "SEGUNDO NOMBRE"},
    {"key": "primer_apellido",    "label": "PRIMER APELLIDO"},
    {"key": "segundo_apellido",   "label": "SEGUNDO APELLIDO"},
    {"key": "document_type",      "label": "TIPO DE DOCUMENTO"},
    {"key": "document_number",    "label": "NUMERO CEDULA"},            # ← obligatoria
    {"key": "birth_date",         "label": "FECHA DE NACIMIENTO"},
    {"key": "role_name",          "label": "ROL ASIGANDO"},
    {"key": "gender",             "label": "GENERO"},
    {"key": "eps_name",           "label": "EPS"},
    {"key": "pension_fund_name",  "label": "PENSION"},
    {"key": "address",            "label": "DIRECCION DE VIVIENDA"},
    {"key": "phone",              "label": "NUMERO DE CELULAR"},
    {"key": "emergency_name",     "label": "NOMBRE CONTACTO EN CASO DE EMERGENCIA"},
    {"key": "emergency_phone",    "label": "TELEFONO CONTACTO EN CASO DE EMERGENCIA"},
    {"key": "coordinator_name",   "label": "COORDINADOR QUE LO PROGRAMA"},
    {"key": "stage",              "label": "ETAPA"},
]

# Columna obligatoria (clave interna).
REQUIRED_KEYS = {"document_number"}


def _normalize_stage(raw) -> tuple[str, bool]:
    """Normaliza la columna ETAPA del Excel.

    Valores válidos: previa, avanzada, evento, desmontaje (sin acentos,
    case-insensitive). Vacío/None → ('evento', True) para mantener
    compatibilidad con plantillas legacy que no traen la columna.

    Retorna (stage, es_valida). Si no es válida retorna ('evento', False)
    para que el caller emita un warning por fila.
    """
    if raw is None or not str(raw).strip():
        return DEFAULT_STAGE, True
    s = _strip_accents(str(raw)).strip().lower()
    if s in EVENT_STAGES:
        return s, True
    return DEFAULT_STAGE, False


# ──────────────────────────────────────────────
#  Helpers de normalización (portados del script CLI)
# ──────────────────────────────────────────────

def _strip_accents(s: str) -> str:
    """Quita acentos/tildes de un string."""
    if not s:
        return ""
    nfkd = unicodedata.normalize("NFKD", s)
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def _norm_header(s: str) -> str:
    """Normaliza un encabezado para matching flexible: UPPER + sin acentos + colapsar espacios."""
    if not s:
        return ""
    s = _strip_accents(str(s)).upper().strip()
    s = re.sub(r"\s+", " ", s)
    return s


def _normalize_eps(name: str) -> str:
    """Normaliza un nombre de EPS para matching fuzzy."""
    if not name:
        return ""
    s = _strip_accents(name).upper().strip()
    for term in [
        "E.P.S.", "E.P.S", "EPS", "EPSS", "S.A.", "S.A", "SA",
        "LTDA.", "LTDA", "S.A.S.", "S.A.S", "SAS",
        "DE SALUD", "ENTIDAD PROMOTORA DE SALUD",
        "DIR.", "DIRECCION", "GENERAL", "FUERZAS", "MILITAR", "MILITARES",
        ".", ",", "-", "_",
    ]:
        s = s.replace(term, " ")
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _normalize_phone(phone: str) -> str:
    """Limpia un teléfono: deja solo dígitos."""
    if not phone:
        return ""
    digits = re.sub(r"\D", "", str(phone))
    return digits[:20] if digits else ""


def _parse_date(date_val) -> Optional[datetime.date]:
    """Convierte varios formatos de fecha → date. Retorna None si falla."""
    if not date_val:
        return None
    # Si ya es un objeto date/datetime (openpyxl puede devolverlo)
    if hasattr(date_val, "year") and hasattr(date_val, "month"):
        return date_val if not hasattr(date_val, "hour") else date_val.date()
    s = str(date_val).strip()
    for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y", "%d.%m.%Y"):
        try:
            return datetime.strptime(s, fmt).date()
        except (ValueError, TypeError):
            continue
    return None


def _build_password(document_number: str, document_type: str) -> str:
    """Genera la contraseña: NumeroDocumento + TipoDocumento (sin acentos).

    Ejemplo: 1027522598 + CC = 1027522598CC
    """
    doc = _strip_accents(str(document_number or "")).strip()
    tipo = _strip_accents(str(document_type or "")).strip().upper()
    return f"{doc}{tipo}"


def _normalize_doc_type(raw: str) -> str:
    """Normaliza el tipo de documento a CC, CE, TI, etc."""
    if not raw:
        return "CC"
    s = _strip_accents(str(raw)).upper().strip()
    mapping = {
        "CEDULA DE CIUDADANIA": "CC",
        "CEDULA CIUDADANIA": "CC",
        "C.C.": "CC",
        "CC": "CC",
        "CEDULA DE EXTRANJERIA": "CE",
        "CEDULA EXTRANJERIA": "CE",
        "C.E.": "CE",
        "CE": "CE",
        "TARJETA DE IDENTIDAD": "TI",
        "TARJETA IDENTIDAD": "TI",
        "T.I.": "TI",
        "TI": "TI",
        "PASAPORTE": "PA",
        "PA": "PA",
    }
    return mapping.get(s, s[:10] if s else "CC")


def _compose_name(primer_nombre, segundo_nombre, primer_apellido, segundo_apellido):
    """Compone first_name y last_name desde las 4 columnas del Excel."""
    first_parts = [p for p in [primer_nombre, segundo_nombre] if p and str(p).strip()]
    last_parts = [p for p in [primer_apellido, segundo_apellido] if p and str(p).strip()]
    first_name = " ".join(str(p).strip() for p in first_parts) if first_parts else ""
    last_name = " ".join(str(p).strip() for p in last_parts) if last_parts else ""
    return first_name, last_name


# ──────────────────────────────────────────────
#  Matching de catálogos (roles, EPS, pensiones)
# ──────────────────────────────────────────────

def _match_role(role_name: str, role_map: dict) -> Optional[uuid.UUID]:
    """Matching fuzzy del rol. role_map = {norm_name: role_id}."""
    if not role_name:
        return None
    norm = _strip_accents(str(role_name)).upper().strip()
    norm_singular = re.sub(r"S$", "", norm)

    # Match exacto
    for key, rid in role_map.items():
        key_norm = _strip_accents(str(key)).upper().strip()
        if key_norm == norm or key_norm == norm_singular:
            return rid

    # Match parcial (contains) con aislamiento de roles "Avanzada":
    # si el texto trae "AVANZAD" solo se aceptan roles avanzados, y si no lo
    # trae solo se aceptan roles básicos (evita que "Operador Logístico"
    # caiga en "Operador Logístico Avanzada" o viceversa).
    wants_advanced = "AVANZAD" in norm
    candidates: list[tuple[str, uuid.UUID]] = []
    for key, rid in role_map.items():
        key_norm = _strip_accents(str(key)).upper().strip()
        if ("AVANZAD" in key_norm) != wants_advanced:
            continue
        if norm in key_norm or key_norm in norm:
            candidates.append((key_norm, rid))
            continue
        if "BRIGADISTA" in norm and "BRIGADISTA" in key_norm:
            candidates.append((key_norm, rid))
            continue
        if "OPERADOR" in norm and "LOGIST" in norm and "LOGIST" in key_norm:
            candidates.append((key_norm, rid))
    if candidates:
        # Empate: gana el candidato más largo (más específico).
        return max(candidates, key=lambda t: len(t[0]))[1]

    return None


def _match_eps(eps_name: str, eps_list: list) -> Optional[uuid.UUID]:
    """Matching fuzzy de EPS. eps_list = [(id, norm_name, raw_name), ...]."""
    if not eps_name:
        return None
    norm = _normalize_eps(str(eps_name))

    # Match exacto normalizado
    for eid, ename_norm, _ in eps_list:
        if ename_norm == norm:
            return eid

    # Match parcial
    for eid, ename_norm, _ in eps_list:
        if not ename_norm or not norm:
            continue
        if ename_norm in norm or norm in ename_norm:
            return eid

    # Keywords
    keywords_map = {
        "SURA": "SURA", "SANITAS": "SANITAS", "NUEVA": "NUEVA",
        "COMPENSAR": "COMPENSAR", "FAMISANAR": "FAMISANAR",
        "SALUD TOTAL": "SALUD TOTAL", "CAPITAL SALUD": "CAPITAL SALUD",
        "SOS": "SERVICIO OCCIDENTAL",
    }
    norm_upper = norm.upper()
    for kw, eps_kw in keywords_map.items():
        if kw in norm_upper:
            for eid, ename_norm, _ in eps_list:
                if eps_kw.upper() in ename_norm.upper():
                    return eid
    return None


def _match_pension_fund(name: str, pf_list: list) -> Optional[uuid.UUID]:
    """Matching fuzzy de fondo de pensiones. pf_list = [(id, norm_name), ...]."""
    if not name:
        return None
    norm = _strip_accents(str(name)).upper().strip()
    for term in ["S.A.", "S.A", "SA", "LTDA.", "LTDA", "S.A.S.", "S.A.S", "SAS", ".", ","]:
        norm = norm.replace(term, " ")
    norm = re.sub(r"\s+", " ", norm).strip()

    # Match exacto
    for pid, pname_norm in pf_list:
        if pname_norm == norm:
            return pid

    # Match parcial
    for pid, pname_norm in pf_list:
        if not pname_norm or not norm:
            continue
        if pname_norm in norm or norm in pname_norm:
            return pid

    # Keywords comunes
    keywords_map = {
        "PORVENIR": "PORVENIR", "COLFONDOS": "COLFONDOS", "PROTECCION": "PROTECCION",
        "OLD MUTUAL": "OLD MUTUAL", "SKANDIA": "SKANDIA",
    }
    for kw in keywords_map:
        if kw in norm:
            for pid, pname_norm in pf_list:
                if kw in pname_norm:
                    return pid
    return None


# ──────────────────────────────────────────────
#  Generación del Excel plantilla
# ──────────────────────────────────────────────

def build_template() -> bytes:
    """Genera el .xlsx plantilla con encabezados oficiales (sin datos de ejemplo)."""
    wb = Workbook()
    ws = wb.active
    ws.title = "Operadores"

    header_font = Font(bold=True, color="FFFFFF", size=11)
    header_fill = PatternFill(start_color="2563EB", end_color="2563EB", fill_type="solid")
    header_align = Alignment(horizontal="center", vertical="center", wrap_text=True)

    # Encabezados
    headers = [c["label"] for c in EXPECTED_COLUMNS]
    for col_idx, header in enumerate(headers, 1):
        cell = ws.cell(row=1, column=col_idx, value=header)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = header_align

    # (Sin fila de ejemplo: la plantilla se entrega vacía, solo con encabezados.)

    # Anchos de columna
    col_widths = [16, 16, 16, 16, 14, 16, 16, 22, 12, 22, 18, 28, 16, 28, 22, 22, 12]
    for i, w in enumerate(col_widths, 1):
        ws.column_dimensions[ws.cell(row=1, column=i).column_letter].width = w

    # Congelar primera fila
    ws.freeze_panes = "A2"

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


# ──────────────────────────────────────────────
#  Lectura del Excel
# ──────────────────────────────────────────────

def _read_excel(file_bytes: bytes) -> list[dict]:
    """Lee el .xlsx y retorna lista de dicts (clave interna → valor).

    Hace matching flexible de encabezados (UPPER + sin acentos).
    Lanza ValueError con detalle si faltan columnas requeridas.
    """
    wb = load_workbook(io.BytesIO(file_bytes), data_only=True, read_only=True)
    ws = wb.active

    # Leer encabezados reales del Excel (fila 1)
    raw_headers = []
    for cell in next(ws.iter_rows(min_row=1, max_row=1)):
        raw_headers.append(str(cell.value).strip() if cell.value is not None else "")

    # Mapear encabezados reales → clave interna (matching flexible)
    norm_to_key = {}
    for col in EXPECTED_COLUMNS:
        norm_to_key[_norm_header(col["label"])] = col["key"]

    header_map = {}  # {col_index: key}
    found_keys = set()
    for col_idx, raw_h in enumerate(raw_headers, 1):
        norm_h = _norm_header(raw_h)
        if norm_h in norm_to_key:
            key = norm_to_key[norm_h]
            if key not in found_keys:  # evitar duplicados
                header_map[col_idx] = key
                found_keys.add(key)

    # Validar columnas requeridas
    missing = REQUIRED_KEYS - found_keys
    if missing:
        labels = []
        for col in EXPECTED_COLUMNS:
            if col["key"] in missing:
                labels.append(col["label"])
        raise ValueError(
            f"Faltan columnas obligatorias en el Excel: {', '.join(labels)}"
        )

    # Leer filas de datos
    rows = []
    for row in ws.iter_rows(min_row=2, values_only=False):
        # Saltar filas completamente vacías
        if all(cell.value is None or str(cell.value).strip() == "" for cell in row):
            continue
        row_dict = {}
        for col_idx, key in header_map.items():
            if col_idx <= len(row):
                val = row[col_idx - 1].value
                row_dict[key] = val if val is not None else None
            else:
                row_dict[key] = None
        rows.append(row_dict)

    wb.close()
    return rows


# ──────────────────────────────────────────────
#  Validación de una fila
# ──────────────────────────────────────────────

def _validate_row(row: dict, row_num: int) -> tuple[dict, list[str]]:
    """Valida una fila. Retorna (datos limpios, lista de errores)."""
    errors = []
    clean = {}

    # Documento obligatorio
    doc_raw = row.get("document_number")
    doc = str(doc_raw).strip() if doc_raw is not None else ""
    # Limpiar el documento: solo dígitos (algunos Excel vienen con formato numérico)
    if isinstance(doc_raw, float):
        doc = str(int(doc_raw))
    doc = re.sub(r"\D", "", doc)
    if not doc:
        errors.append("Número de documento vacío")
    clean["document_number"] = doc

    # Composición de nombres
    first_name, last_name = _compose_name(
        row.get("primer_nombre"),
        row.get("segundo_nombre"),
        row.get("primer_apellido"),
        row.get("segundo_apellido"),
    )
    clean["first_name"] = first_name or ""
    clean["last_name"] = last_name or "SIN APELLIDO"  # DB requiere non-null
    # Presencia real de nombres: en UPDATE los placeholders ("SIN APELLIDO",
    # nombre vacío) no deben pisar valores existentes.
    clean["first_name_present"] = bool(first_name)
    clean["last_name_present"] = bool(
        row.get("primer_apellido") or row.get("segundo_apellido")
    )

    # Tipo de documento
    doc_type = _normalize_doc_type(row.get("document_type"))
    clean["document_type"] = doc_type

    # Fecha de nacimiento
    clean["birth_date"] = _parse_date(row.get("birth_date"))

    # Género
    gender_raw = row.get("gender")
    clean["gender"] = str(gender_raw).strip() if gender_raw else None

    # Rol
    clean["role_name"] = str(row.get("role_name") or "").strip() or None

    # EPS
    clean["eps_name"] = str(row.get("eps_name") or "").strip() or None

    # Pensión
    clean["pension_fund_name"] = str(row.get("pension_fund_name") or "").strip() or None

    # Dirección
    addr_raw = row.get("address")
    clean["address"] = str(addr_raw).strip() if addr_raw else None

    # Teléfono
    clean["phone"] = _normalize_phone(row.get("phone")) or None

    # Contacto de emergencia
    em_name = row.get("emergency_name")
    clean["emergency_name"] = str(em_name).strip() if em_name else None
    clean["emergency_phone"] = _normalize_phone(row.get("emergency_phone")) or None

    # Coordinador
    coord_raw = row.get("coordinator_name")
    clean["coordinator_name"] = str(coord_raw).strip() if coord_raw else None

    # Etapa (columna opcional ETAPA; default 'evento')
    stage_norm, stage_ok = _normalize_stage(row.get("stage"))
    clean["stage"] = stage_norm
    if not stage_ok:
        clean["stage_invalid"] = str(row.get("stage")).strip()

    return clean, errors


# ──────────────────────────────────────────────
#  Pre-carga de catálogos (batch, evita N+1)
# ──────────────────────────────────────────────

async def _load_role_map(db: AsyncSession) -> dict:
    """Carga roles en un dict {norm_name: id}."""
    result = await db.execute(text("SELECT id, name FROM roles WHERE is_active = true"))
    role_map = {}
    for row in result:
        norm = _strip_accents(row.name).upper().strip()
        role_map[norm] = row.id
        role_map[row.name.strip().upper()] = row.id  # también sin normalizar
    return role_map


async def _load_eps_list(db: AsyncSession) -> list:
    """Carga EPS como [(id, norm_name, raw_name), ...]."""
    result = await db.execute(text("SELECT id, name FROM eps WHERE is_active = true"))
    return [(r.id, _normalize_eps(r.name), r.name) for r in result]


async def _load_pension_fund_list(db: AsyncSession) -> list:
    """Carga fondos de pensión como [(id, norm_name), ...]."""
    result = await db.execute(text("SELECT id, name FROM pension_fund"))
    return [(r.id, _strip_accents(r.name).upper().strip()) for r in result]


async def _load_coordinators(db: AsyncSession, event_id: uuid.UUID) -> list:
    """Carga coordinadores del evento desde EventCoordinatorQuota.

    Retorna [(operator_id, norm_name, display_name, stage), ...].
    Incluye coordinadores legacy (sin operator_id) y del nuevo flujo (con FK).
    """
    result = await db.execute(
        text("""
            SELECT coordinator_operator_id, coordinator, stage
            FROM event_coordinator_quotas
            WHERE event_id = :eid
        """),
        {"eid": str(event_id)},
    )
    coords = []
    for r in result:
        norm = _strip_accents(r.coordinator).upper().strip()
        op_id = str(r.coordinator_operator_id) if r.coordinator_operator_id else None
        coords.append((op_id, norm, r.coordinator, r.stage or DEFAULT_STAGE))
    return coords


async def _ensure_coordinator_quotas(
    db: AsyncSession, event_id: uuid.UUID,
    excel_coords: dict, existing_coords: list,
) -> tuple[int, int, list]:
    """Sincroniza quotas de coordinadores desde el Excel.

    Para cada coordinador del Excel:
    - Si YA tiene quota: la actualiza al count exacto del Excel (source of truth).
    - Si NO tiene quota: la crea como LEGACY (sin FK, texto libre).

    IMPORTANTE: NO se hace matching por nombre contra TODOS los operadores de la BD.
    Eso asignaba FKs falsas a operadores que no son coordinadores. La FK solo se
    conserva si el coordinador ya existía en event_coordinator_quotas con FK
    (es decir, fue cargado manualmente por el admin en crear/editar evento).
    Los coordinadores nuevos del Excel se guardan como legacy (sin FK).

    Args:
        excel_coords: {(norm_name, stage): (display_name, count)} del Excel.
        existing_coords: lista de coordinadores ya con quota.

    Returns:
        (num_created, num_updated, updated_coords_list).
    """
    created = 0
    updated = 0

    for (cnorm, stage), (display, count) in excel_coords.items():
        # Buscar match exacto en las quotas existentes (nombre + etapa).
        matched = None
        for item in existing_coords:
            ex_op_id, ex_norm, ex_display, ex_stage = item
            if cnorm == ex_norm and ex_stage == stage:
                matched = item
                break

        if matched:
            # Ya tiene quota en esta etapa → actualizar al count exacto del Excel.
            ex_op_id, ex_norm, ex_display, ex_stage = matched
            await db.execute(text("""
                UPDATE event_coordinator_quotas
                SET quota = :quota
                WHERE event_id = :eid AND coordinator = :coord_name
                  AND stage = :stage
            """), {
                "eid": str(event_id),
                "coord_name": ex_display,
                "stage": stage,
                "quota": count,
            })
            updated += 1
            continue

        # No tiene quota → crear como LEGACY (sin FK, texto libre).
        # NO se resuelve coordinator_operator_id contra operadores de la BD.
        display_upper = _strip_accents(display).upper().strip()

        try:
            await db.execute(text("""
                INSERT INTO event_coordinator_quotas (
                    id, event_id, coordinator, coordinator_operator_id, quota, stage
                ) VALUES (
                    gen_random_uuid(), :eid, :coord, NULL, :quota, :stage
                )
                ON CONFLICT DO NOTHING
            """), {
                "eid": str(event_id),
                "coord": display_upper,
                "quota": count,
                "stage": stage,
            })
            created += 1
            existing_coords.append((None, cnorm, display_upper, stage))
        except Exception:
            pass

    return created, updated, existing_coords


def _resolve_coordinator(coord_name: str, coords: list) -> tuple[Optional[uuid.UUID], Optional[str]]:
    """Busca un coordinador por nombre en la lista de coordinadores del evento.

    Retorna (operator_id, display_name). Si no hay match → (None, coord_name original).

    IMPORTANTE: El matching es ESTRICTO para evitar que un nombre del Excel (ej:
    'SANDRA R') se reparta a múltiples coordinadores cuyos nombres comparten
    tokens (ej: 'SANDRA RAMIREZ' y 'SANDRA RIOS'). Solo se acepta un match parcial
    cuando hay EXACTAMENTE UN candidato, evitando ambigüedad.
    """
    if not coord_name:
        return None, None
    norm = _strip_accents(str(coord_name)).upper().strip()
    norm_tokens = norm.split()

    # 1. Match exacto normalizado
    for op_id, c_norm, display, _stage in coords:
        if c_norm == norm:
            return op_id, display

    # 2. Match por iniciales: cada token del input es prefijo del token
    #    correspondiente del coordinador (ej: 'SANDRA R' → 'SANDRA RAMIREZ').
    #    Solo si hay un único candidato.
    if len(norm_tokens) >= 2:
        candidates = []
        for op_id, c_norm, display, _stage in coords:
            c_tokens = c_norm.split()
            if len(c_tokens) >= len(norm_tokens) and all(
                c_tokens[i].startswith(norm_tokens[i]) for i in range(len(norm_tokens))
            ):
                candidates.append((op_id, c_norm, display))
        if len(candidates) == 1:
            return candidates[0][0], candidates[0][2]

    # 3. El input es prefijo del nombre completo (ej: 'SANDRA' → 'SANDRA RAMIREZ').
    #    Solo si hay un único candidato.
    prefix_candidates = [
        (op_id, c_norm, display)
        for op_id, c_norm, display, _stage in coords
        if c_norm and c_norm.startswith(norm)
    ]
    if len(prefix_candidates) == 1:
        return prefix_candidates[0][0], prefix_candidates[0][2]

    # 4. Match por primer token exacto, solo si hay un único candidato.
    first_token = norm_tokens[0] if norm_tokens else ""
    if first_token:
        first_token_candidates = [
            (op_id, c_norm, display)
            for op_id, c_norm, display, _stage in coords
            if c_norm.split() and c_norm.split()[0] == first_token
        ]
        if len(first_token_candidates) == 1:
            return first_token_candidates[0][0], first_token_candidates[0][2]

    # No match → texto libre
    return None, _strip_accents(str(coord_name)).upper().strip()


async def _load_existing_users_by_doc(db: AsyncSession, doc_numbers: list[str]) -> dict:
    """Carga user_id+operator_id existentes por document_number.

    Retorna {document_number: (user_id, operator_id)}.
    """
    if not doc_numbers:
        return {}
    # Query en lotes para evitar SQL demasiado grande
    result = {}
    batch_size = 500
    for i in range(0, len(doc_numbers), batch_size):
        batch = doc_numbers[i:i + batch_size]
        placeholders = ",".join(f":d{j}" for j in range(len(batch)))
        params = {f"d{j}": batch[j] for j in range(len(batch))}
        rows = await db.execute(text(f"""
            SELECT u.id AS user_id, u.document_number,
                   (SELECT o.id FROM operators o WHERE o.user_id = u.id) AS operator_id
            FROM users u
            WHERE u.document_number IN ({placeholders})
        """), params)
        for r in rows:
            result[str(r.document_number)] = (r.user_id, r.operator_id)
    return result


async def _load_assigned_operators(db: AsyncSession, event_id: uuid.UUID) -> dict:
    """Carga {(operator_id, stage): role_id} de las asignaciones del evento.

    Mantiene la membresía del set original (sin filtro is_active) para no
    cambiar la semántica de detección, pero prefiere el role_id de la fila
    activa cuando hay históricos inactivos. La clave incluye la ETAPA: el
    mismo operador puede tener una asignación por cada etapa (doble turno).
    """
    result = await db.execute(
        text(
            "SELECT operator_id, role_id, stage, is_active "
            "FROM event_assignments WHERE event_id = :eid "
            "ORDER BY is_active DESC"
        ),
        {"eid": str(event_id)},
    )
    out: dict = {}
    for r in result:
        key = (r.operator_id, r.stage or DEFAULT_STAGE)
        if key not in out:
            out[key] = r.role_id
    return out


# ──────────────────────────────────────────────
#  Orquestador principal
# ──────────────────────────────────────────────

async def import_operators_from_excel(
    db: AsyncSession, file_bytes: bytes, event_id: uuid.UUID,
    progress_cb=None,
) -> ImportSummary:
    """Procesa el Excel completo y devuelve un ImportSummary.

    Flujo:
      1. Lee el Excel.
      2. Pre-carga catálogos (roles, EPS, pensiones, coordinadores, usuarios existentes).
      3. Pre-hashing PARALELO de contraseñas de operadores nuevos (bcrypt
         libera el GIL → hashing en ThreadPool real; ~8x más rápido con 8 CPUs).
      4. Por cada fila: valida, crea/asigna, registra resultado.
      5. Commit único.

    ``progress_cb(processed, total, stage)`` permite reportar avance
    (stage: 'hashing' | 'processing'); lo consume el job en background
    (app.services.import_jobs) para el polling del frontend.
    """
    t0 = time.time()
    rows_result: list[ImportRowResult] = []
    created = 0
    existing = 0
    already_assigned = 0
    updated = 0
    errors = 0

    # --- 1. Leer Excel ---
    try:
        raw_rows = _read_excel(file_bytes)
    except ValueError as exc:
        return ImportSummary(
            total_rows=0, created=0, existing=0, already_assigned=0,
            assigned=0, errors=1, duration_seconds=0.0,
            rows=[ImportRowResult(
                row=0, status="error",
                message=f"Error leyendo Excel: {exc}",
            )],
        )

    if not raw_rows:
        return ImportSummary(
            total_rows=0, created=0, existing=0, already_assigned=0,
            assigned=0, errors=0, duration_seconds=0.0, rows=[],
        )

    # --- 2. Pre-carga batch ---
    role_map = await _load_role_map(db)
    eps_list = await _load_eps_list(db)
    pf_list = await _load_pension_fund_list(db)
    coords = await _load_coordinators(db, event_id)

    # Documentos del Excel (para batch query de existentes)
    all_docs = []
    for raw in raw_rows:
        doc_val = raw.get("document_number")
        if doc_val is not None:
            d = str(doc_val).strip()
            if isinstance(doc_val, float):
                d = str(int(doc_val))
            d = re.sub(r"\D", "", d)
            if d:
                all_docs.append(d)

    existing_users = await _load_existing_users_by_doc(db, list(set(all_docs)))
    assigned_ops = await _load_assigned_operators(db, event_id)

    # --- 2a. Pre-validación + pre-hash PARALELO de contraseñas ---
    # bcrypt cuesta ~350ms por operador. Para 1000+ filas nuevas eso son
    # ~6 minutos SI se hace secuencial dentro del loop. Haciéndolo aquí en
    # paralelo (asyncio.to_thread: bcrypt libera el GIL) el costo baja a
    # total*0.35/n_cpus segundos, sin cambiar el resultado final.
    pre_validated: dict[int, tuple[dict, list[str]]] = {}
    _pre_seen: set[str] = set()
    pending_pws: dict[str, str] = {}
    for idx, raw in enumerate(raw_rows, 1):
        clean, val_errors = _validate_row(raw, idx)
        pre_validated[idx] = (clean, val_errors)
        doc = clean["document_number"]
        if val_errors or not doc or doc in _pre_seen:
            continue
        _pre_seen.add(doc)
        if doc not in existing_users:
            pending_pws[doc] = _build_password(doc, clean["document_type"])

    pw_hashes: dict[str, str] = {}
    if pending_pws:
        docs_to_hash = list(pending_pws.keys())
        total_hash = len(docs_to_hash)
        # Chunks para no crear miles de threads de golpe; el pool por defecto
        # limita la concurrencia real a ~min(32, cpus+4).
        CHUNK = 64
        done = 0
        for i in range(0, total_hash, CHUNK):
            chunk = docs_to_hash[i:i + CHUNK]
            hashes = await asyncio.gather(*[
                asyncio.to_thread(hash_password, pending_pws[d]) for d in chunk
            ])
            for d, h in zip(chunk, hashes):
                pw_hashes[d] = h
            done += len(chunk)
            if progress_cb:
                progress_cb(done, total_hash, "hashing")

    # --- 2b. Auto-crear quotas de coordinadores faltantes ---
    # Recolectar coordinadores únicos del Excel con su conteo de operadores,
    # separados por ETAPA (un coordinador puede tener cupo distinto en cada
    # etapa del mismo evento).
    excel_coords: dict[tuple[str, str], tuple[str, int]] = {}  # {(norm, stage): (display, count)}
    for raw in raw_rows:
        coord_val = raw.get("coordinator_name")
        if not coord_val or not str(coord_val).strip():
            continue
        stage, _stage_ok = _normalize_stage(raw.get("stage"))
        display = _strip_accents(str(coord_val)).upper().strip()
        cnorm = display
        key = (cnorm, stage)
        if key not in excel_coords:
            excel_coords[key] = (display, 0)
        # Incrementar el conteo de operadores para este coordinador+etapa
        prev_display, prev_count = excel_coords[key]
        excel_coords[key] = (prev_display, prev_count + 1)

    # Sincronizar quotas: crea las faltantes y actualiza las existentes al
    # count exacto del Excel (source of truth).
    created_quotas, updated_quotas, coords = await _ensure_coordinator_quotas(
        db, event_id, excel_coords, coords,
    )

    # Detección de duplicados dentro del Excel: mismo documento EN LA MISMA
    # etapa es error; el mismo operador en etapas distintas es legítimo
    # (doble turno: p. ej. 'previa' + 'evento').
    seen_keys: set[tuple[str, str]] = set()

    now_utc = datetime.now(timezone.utc)

    # --- 3. Procesar filas ---
    for idx, raw in enumerate(raw_rows, 1):
        if progress_cb and (idx % 20 == 0 or idx == len(raw_rows)):
            progress_cb(idx, len(raw_rows), "processing")
        clean, val_errors = pre_validated[idx]
        doc = clean["document_number"]
        full_name = f"{clean['first_name']} {clean['last_name']}".strip()
        stage = clean.get("stage") or DEFAULT_STAGE

        # Error de validación
        if val_errors:
            errors += 1
            rows_result.append(ImportRowResult(
                row=idx, document_number=doc or None, full_name=full_name or None,
                status="error", message="; ".join(val_errors),
            ))
            continue

        # Duplicado dentro del mismo Excel (misma etapa)
        if (doc, stage) in seen_keys:
            errors += 1
            rows_result.append(ImportRowResult(
                row=idx, document_number=doc, full_name=full_name,
                status="error",
                message=f"Documento duplicado en la etapa '{stage}': {doc}",
            ))
            continue
        seen_keys.add((doc, stage))

        warnings = []
        if "stage_invalid" in clean:
            bad = clean.pop("stage_invalid")
            warnings.append(
                f"Etapa '{bad}' no válida — se usó 'evento' "
                "(válidas: previa, avanzada, evento, desmontaje)"
            )

        # --- Resolver catálogos ---
        role_id = _match_role(clean["role_name"], role_map) if clean["role_name"] else None
        if clean["role_name"] and not role_id:
            warnings.append(f"Rol '{clean['role_name']}' no encontrado")

        eps_id = _match_eps(clean["eps_name"], eps_list) if clean["eps_name"] else None
        if clean["eps_name"] and not eps_id:
            warnings.append(f"EPS '{clean['eps_name']}' no encontrada")

        pf_id = _match_pension_fund(clean["pension_fund_name"], pf_list) if clean["pension_fund_name"] else None
        if clean["pension_fund_name"] and not pf_id:
            warnings.append(f"Pensión '{clean['pension_fund_name']}' no encontrada")

        coord_op_id, coord_display = _resolve_coordinator(clean["coordinator_name"], coords)

        # --- Caso 1: operador ya existe en BD ---
        if doc in existing_users:
            user_id, operator_id = existing_users[doc]
            if operator_id and (operator_id, stage) in assigned_ops:
                # Ya asignado a este evento → actualizar cargo del evento,
                # datos de perfil y coordinador con lo que traiga el Excel.
                # Regla: un campo vacío del Excel NUNCA borra el valor
                # existente (semántica COALESCE).
                current_role_id = assigned_ops[(operator_id, stage)]
                new_role_id, role_changed = _resolve_role_update(
                    current_role_id, clean["role_name"], role_id,
                )

                profile_changed = await _update_user_fields(db, user_id, clean)
                profile_changed = (await _update_operator_profile_fields(
                    db, operator_id, eps_id, pf_id, clean,
                )) or profile_changed
                coord_changed = await _update_assignment_coordinator(
                    db, event_id, operator_id, coord_op_id, coord_display, stage,
                )
                if role_changed:
                    await _update_assignment_role(
                        db, event_id, operator_id, new_role_id, stage,
                    )
                    assigned_ops[(operator_id, stage)] = new_role_id

                if role_changed or profile_changed or coord_changed:
                    updated += 1
                    changes = []
                    if role_changed:
                        changes.append("cargo")
                    if profile_changed:
                        changes.append("datos personales")
                    if coord_changed:
                        changes.append("coordinador")
                    rows_result.append(ImportRowResult(
                        row=idx, document_number=doc, full_name=full_name,
                        status="updated",
                        message="Ya estaba asignado — actualizado: "
                                + ", ".join(changes),
                        operator_id=str(operator_id),
                        warnings=warnings,
                    ))
                else:
                    already_assigned += 1
                    rows_result.append(ImportRowResult(
                        row=idx, document_number=doc, full_name=full_name,
                        status="already_assigned",
                        message="Ya estaba asignado a este evento — sin cambios",
                        operator_id=str(operator_id),
                        warnings=warnings,
                    ))
                continue

            # Asignar existente al evento
            if operator_id:
                await _create_assignment(
                    db, event_id, operator_id, role_id,
                    coord_op_id, coord_display, stage,
                )
                assigned_ops[(operator_id, stage)] = role_id
                existing += 1
                rows_result.append(ImportRowResult(
                    row=idx, document_number=doc, full_name=full_name,
                    status="existing",
                    message="Operador existente asignado al evento",
                    operator_id=str(operator_id),
                    warnings=warnings,
                ))
                continue
            else:
                # Existe el user pero no el operator profile → crear profile
                operator_id = await _create_operator_profile(
                    db, user_id, eps_id, pf_id, clean, role_id,
                )
                existing_users[doc] = (user_id, operator_id)

        # --- Caso 2: operador nuevo ---
        else:
            # Generar email y contraseña
            email = f"{doc}@operador.temp"
            password = _build_password(doc, clean["document_type"])

            try:
                user_id = await _create_user(
                    db, email, password, clean, role_id,
                    pw_hash=pw_hashes.get(doc),
                )
            except Exception as exc:
                errors += 1
                rows_result.append(ImportRowResult(
                    row=idx, document_number=doc, full_name=full_name,
                    status="error", message=f"Error creando usuario: {exc}",
                ))
                continue

            try:
                operator_id = await _create_operator_profile(
                    db, user_id, eps_id, pf_id, clean, role_id,
                )
            except Exception as exc:
                errors += 1
                rows_result.append(ImportRowResult(
                    row=idx, document_number=doc, full_name=full_name,
                    status="error", message=f"Error creando perfil: {exc}",
                ))
                continue

            existing_users[doc] = (user_id, operator_id)

        # --- Asignar al evento ---
        if operator_id and (operator_id, stage) not in assigned_ops:
            await _create_assignment(
                db, event_id, operator_id, role_id,
                coord_op_id, coord_display, stage,
            )
            assigned_ops[(operator_id, stage)] = role_id
            created += 1
            rows_result.append(ImportRowResult(
                row=idx, document_number=doc, full_name=full_name,
                status="created",
                message="Operador creado y asignado al evento",
                operator_id=str(operator_id),
                warnings=warnings,
            ))

    # --- 4. Recalcular quantity_confirmed (personal requerido) ---
    # La importación crea asignaciones con status='confirmed' pero no toca
    # el contador quantity_confirmed de event_staff_needs. Recalcular desde
    # la fuente de verdad (asignaciones reales) repara drift histórico y
    # refleja los confirmados en la tabla de "personal requerido".
    await _recalculate_confirmed_counts(db, event_id)

    # --- 5. Commit único ---
    await db.commit()

    elapsed = round(time.time() - t0, 2)

    return ImportSummary(
        total_rows=len(raw_rows),
        created=created,
        existing=existing,
        already_assigned=already_assigned,
        updated=updated,
        assigned=created + existing,
        errors=errors,
        duration_seconds=elapsed,
        rows=rows_result,
    )


# ──────────────────────────────────────────────
#  Funciones de creación (SQL crudo, como el script CLI)
# ──────────────────────────────────────────────

async def _create_user(db, email, password, clean, role_id, pw_hash: str | None = None) -> uuid.UUID:
    """Crea un User y retorna su id.

    ``pw_hash`` permite reutilizar un hash pre-calculado en paralelo
    (optimización para archivos grandes); si no llega, hashea en línea.
    """
    pw_hash = pw_hash or hash_password(password)
    result = await db.execute(text("""
        INSERT INTO users (
            id, email, password_hash, first_name, last_name,
            phone, document_type, document_number, user_type,
            role_id, is_verified, is_approved, is_active
        ) VALUES (
            gen_random_uuid(), :email, :pw, :first_name, :last_name,
            :phone, :doc_type, :doc, 'operator',
            :role_id, true, true, true
        )
        RETURNING id
    """), {
        "email": email, "pw": pw_hash,
        "first_name": clean["first_name"][:100],
        "last_name": clean["last_name"][:100],
        "phone": clean.get("phone"),
        "doc_type": clean["document_type"],
        "doc": clean["document_number"],
        "role_id": role_id,
    })
    return result.scalar()


async def _create_operator_profile(db, user_id, eps_id, pf_id, clean, role_id) -> uuid.UUID:
    """Crea un perfil Operator y retorna su id."""
    import json
    experience_roles_json = json.dumps([str(role_id)]) if role_id else None

    result = await db.execute(text("""
        INSERT INTO operators (
            id, user_id, eps_id, pension_fund_id, birth_date, gender, address,
            emergency_contact_name, emergency_contact_phone,
            whatsapp, background_check_status, total_events, is_active,
            experience_roles, has_protocol_experience, event_size_experience,
            is_banned
        ) VALUES (
            gen_random_uuid(), :user_id, :eps_id, :pf_id, :birth_date, :gender, :address,
            :emergency_name, :emergency_phone,
            :whatsapp, 'pending', 0, true,
            :experience_roles, true, '100',
            false
        )
        RETURNING id
    """), {
        "user_id": user_id,
        "eps_id": eps_id,
        "pf_id": pf_id,
        "birth_date": clean.get("birth_date"),
        "gender": clean.get("gender"),
        "address": clean.get("address"),
        "emergency_name": clean.get("emergency_name"),
        "emergency_phone": clean.get("emergency_phone"),
        "whatsapp": clean.get("phone"),
        "experience_roles": experience_roles_json,
    })
    return result.scalar()


async def _create_assignment(db, event_id, operator_id, role_id, coord_op_id, coord_display, stage: str = DEFAULT_STAGE):
    """Crea un EventAssignment con status='confirmed' y datos del coordinador.

    F11 (atribución por referido): si la fila del Excel NO trae coordinador
    (coord_op_id y coord_display vacíos) y el operador tiene referente, el
    REFERENTE se estampa como programmed_by/admitted_by de la asignación.
    R1: el coordinador explícito del Excel siempre gana. R3: solo aplica a
    asignaciones nuevas creadas por el import (UPDATE no cambia).
    """
    # F11 — Fallback por referido cuando no hay coordinador explícito.
    if not coord_op_id and not coord_display:
        referrer = await get_referrer_operator_of(db, operator_id)
        if referrer:
            res = await db.execute(text(
                "SELECT first_name, last_name FROM users WHERE id = :uid"
            ), {"uid": str(referrer.user_id)})
            row = res.first()
            if row:
                coord_display = f"{row.first_name} {row.last_name}".upper()
                coord_op_id = referrer.id
    now_iso = datetime.now(timezone.utc).isoformat()
    await db.execute(text("""
        INSERT INTO event_assignments (
            id, event_id, operator_id, role_id, status, stage,
            confirmed_at, is_active, reminder_sent,
            programmed_by, admitted_by,
            programmed_by_operator_id, admitted_by_operator_id
        ) VALUES (
            gen_random_uuid(), :eid, :oid, :rid, 'confirmed', :stage,
            NOW(), true, false,
            :coord_display, :coord_display,
            :coord_op_id, :coord_op_id
        )
        ON CONFLICT DO NOTHING
    """), {
        "eid": str(event_id),
        "oid": str(operator_id),
        "rid": role_id,
        "stage": stage,
        "coord_display": coord_display,
        "coord_op_id": str(coord_op_id) if coord_op_id else None,
    })


async def _update_assignment_coordinator(
    db, event_id, operator_id, coord_op_id, coord_display,
    stage: str = DEFAULT_STAGE,
) -> bool:
    """Actualiza las FKs/strings de coordinador de una asignación existente.

    Se usa al reimportar un Excel sobre operadores ya asignados: si una
    importación anterior estampó un coordinador equivocado (por matching
    permisivo), esta función lo corrige al coordinador correcto del Excel.
    Solo actualiza si el nuevo coordinador está definido (coord_op_id o
    coord_display); nunca deja la FK en NULL si antes tenía valor y el Excel
    no trae coordinador.

    Retorna True si aplicó cambios (permite distinguir 'updated' de
    'already_assigned' en el resumen de la importación).
    """
    if not coord_op_id and not coord_display:
        return False
    res = await db.execute(text("""
        SELECT programmed_by, programmed_by_operator_id
        FROM event_assignments
        WHERE event_id = :eid AND operator_id = :oid AND is_active = true
          AND stage = :stage
        LIMIT 1
    """), {
        "eid": str(event_id),
        "oid": str(operator_id),
        "stage": stage,
    })
    row = res.first()
    if row is None:
        return False
    if (row.programmed_by or None) == (coord_display or None) and \
            row.programmed_by_operator_id == coord_op_id:
        return False
    await db.execute(text("""
        UPDATE event_assignments
        SET programmed_by = :coord_display,
            admitted_by = :coord_display,
            programmed_by_operator_id = :coord_op_id,
            admitted_by_operator_id = :coord_op_id
        WHERE event_id = :eid
          AND operator_id = :oid
          AND is_active = true
          AND stage = :stage
    """), {
        "eid": str(event_id),
        "oid": str(operator_id),
        "coord_display": coord_display,
        "coord_op_id": str(coord_op_id) if coord_op_id else None,
        "stage": stage,
    })
    return True


def _resolve_role_update(current_role_id, role_name, matched_role_id):
    """Decide el nuevo role_id de la asignación al re-importar la fila.

    Reglas (acordadas con producto):
      - Celda de rol vacía → conserva el cargo actual.
      - Rol matchea en catálogo → usarlo; changed si difiere del actual.
      - Rol NO matchea → la asignación queda sin cargo (NULL); el warning
        "Rol ... no encontrado" ya lo emitió el loop principal.

    Retorna (new_role_id, changed).
    """
    if role_name is None:
        return current_role_id, False
    if matched_role_id is None:
        return None, current_role_id is not None
    return matched_role_id, matched_role_id != current_role_id


async def _update_assignment_role(db, event_id, operator_id, new_role_id, stage: str = DEFAULT_STAGE):
    """Cambia el cargo (role_id) de la asignación activa de esta etapa."""
    await db.execute(text("""
        UPDATE event_assignments
        SET role_id = :rid
        WHERE event_id = :eid
          AND operator_id = :oid
          AND is_active = true
          AND stage = :stage
    """), {
        "eid": str(event_id),
        "oid": str(operator_id),
        "rid": str(new_role_id) if new_role_id else None,
        "stage": stage,
    })


async def _update_user_fields(db, user_id, clean) -> bool:
    """Actualiza datos del User al re-importar (semántica COALESCE).

    Un campo vacío del Excel NO borra el valor existente. Los placeholders
    ("SIN APELLIDO", nombre vacío) se pasan como NULL para no pisar valores.
    Retorna True si aplicó cambios.
    """
    res = await db.execute(text("""
        SELECT first_name, last_name, phone, document_type
        FROM users WHERE id = :uid
    """), {"uid": str(user_id)})
    row = res.first()
    if row is None:
        return False

    new_first = clean["first_name"][:100] if clean.get("first_name_present") else None
    new_last = clean["last_name"][:100] if clean.get("last_name_present") else None
    new_phone = clean.get("phone")
    new_doc_type = clean.get("document_type")

    changed = (
        (new_first is not None and new_first != row.first_name)
        or (new_last is not None and new_last != row.last_name)
        or (new_phone is not None and new_phone != (row.phone or ""))
        or (new_doc_type is not None and new_doc_type != row.document_type)
    )
    if not changed:
        return False

    await db.execute(text("""
        UPDATE users SET
            first_name = COALESCE(NULLIF(:first_name, ''), first_name),
            last_name = COALESCE(NULLIF(:last_name, ''), last_name),
            phone = COALESCE(:phone, phone),
            document_type = COALESCE(:doc_type, document_type)
        WHERE id = :uid
    """), {
        "uid": str(user_id),
        "first_name": new_first,
        "last_name": new_last,
        "phone": new_phone,
        "doc_type": new_doc_type,
    })
    return True


async def _update_operator_profile_fields(db, operator_id, eps_id, pf_id, clean) -> bool:
    """Actualiza el perfil Operator al re-importar (semántica COALESCE).

    EPS/pensión no encontradas en el catálogo llegan como NULL y conservan la
    actual (coherente con la regla "vacío no borra").
    Retorna True si aplicó cambios.
    """
    res = await db.execute(text("""
        SELECT eps_id, pension_fund_id, birth_date, gender, address,
               emergency_contact_name, emergency_contact_phone, whatsapp
        FROM operators WHERE id = :oid
    """), {"oid": str(operator_id)})
    row = res.first()
    if row is None:
        return False

    params = {
        "eps_id": str(eps_id) if eps_id else None,
        "pf_id": str(pf_id) if pf_id else None,
        "birth_date": clean.get("birth_date"),
        "gender": clean.get("gender"),
        "address": clean.get("address"),
        "emergency_name": clean.get("emergency_name"),
        "emergency_phone": clean.get("emergency_phone"),
        "whatsapp": clean.get("phone"),
    }

    def _differs(new, old):
        return new is not None and new != old

    changed = (
        _differs(params["eps_id"], str(row.eps_id) if row.eps_id else None)
        or _differs(params["pf_id"], str(row.pension_fund_id) if row.pension_fund_id else None)
        or _differs(params["birth_date"], row.birth_date)
        or _differs(params["gender"], row.gender)
        or _differs(params["address"], row.address)
        or _differs(params["emergency_name"], row.emergency_contact_name)
        or _differs(params["emergency_phone"], row.emergency_contact_phone)
        or _differs(params["whatsapp"], row.whatsapp)
    )
    if not changed:
        return False

    await db.execute(text("""
        UPDATE operators SET
            eps_id = COALESCE(:eps_id, eps_id),
            pension_fund_id = COALESCE(:pf_id, pension_fund_id),
            birth_date = COALESCE(:birth_date, birth_date),
            gender = COALESCE(NULLIF(:gender, ''), gender),
            address = COALESCE(:address, address),
            emergency_contact_name = COALESCE(:emergency_name, emergency_contact_name),
            emergency_contact_phone = COALESCE(:emergency_phone, emergency_contact_phone),
            whatsapp = COALESCE(:whatsapp, whatsapp)
        WHERE id = :oid
    """), {"oid": str(operator_id), **params})
    return True


async def _recalculate_confirmed_counts(db: AsyncSession, event_id: uuid.UUID) -> None:
    """Recalcula event_staff_needs.quantity_confirmed desde las asignaciones reales.

    Cuenta operadores con status IN ('confirmed', 'checked_in') agrupados por
    rol Y ETAPA (a.stage = esn2.stage), y actualiza el contador de cada cargo.
    Repara drift histórico (p. ej. cuando los operadores se importaron por
    Excel sin actualizar el contador).
    """
    await db.execute(text("""
        UPDATE event_staff_needs esn
        SET quantity_confirmed = sub.cnt
        FROM (
            SELECT esn2.id AS need_id, COALESCE(count(a.id), 0) AS cnt
            FROM event_staff_needs esn2
            LEFT JOIN event_assignments a
                ON a.event_id = esn2.event_id
                AND a.role_id = esn2.role_id
                AND a.stage = esn2.stage
                AND a.status IN ('confirmed', 'checked_in')
                AND a.is_active = true
            WHERE esn2.event_id = :eid
            GROUP BY esn2.id
        ) sub
        WHERE esn.id = sub.need_id
    """), {"eid": str(event_id)})
