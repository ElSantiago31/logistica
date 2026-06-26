"""Importador masivo de operadores desde JSON.

Crea usuarios (user_type=operator) + perfil Operator para cada registro.
Si se pasa --event, también asigna cada operador al evento.

USO:
    # Solo crear operadores (sin asignar a evento):
    python -m scripts.import_operators

    # Crear operadores + asignar a un evento con status 'confirmed':
    python -m scripts.import_operators --event <EVENT_UUID> --status confirmed

    # Usar otro archivo JSON:
    python -m scripts.import_operators --file scripts/data/otros.json

CONTRASEÑA:
    Cada operador recibe como contraseña: PrimerNombre + NúmeroDocumento
    Ejemplo: Santiago1027522598
"""
import asyncio
import json
import os
import re
import sys
import unicodedata
import uuid
from datetime import datetime
from pathlib import Path

# Forzar UTF-8 en stdout/stderr (Windows usa cp1252 por defecto)
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except (AttributeError, Exception):
    pass

# Asegurar que backend/ esté en sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

from app.config import settings
from app.services.auth import hash_password

# ──────────────────────────────────────────────
#  Helpers
# ──────────────────────────────────────────────

def _strip_accents(s: str) -> str:
    """Quita acentos/tildes de un string."""
    if not s:
        return ""
    nfkd = unicodedata.normalize("NFKD", s)
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def _normalize_eps(name: str) -> str:
    """Normaliza un nombre de EPS para matching fuzzy.

    Quita acentos, mayúsculas, y términos redundantes (E.P.S., S.A., LTDA, EPSS, etc.)
    para poder comparar 'NUEVA E.P.S. S.A.' con 'Nueva EPS'.
    """
    if not name:
        return ""
    s = _strip_accents(name).upper().strip()
    # Quitar términos redundantes
    for term in [
        "E.P.S.", "E.P.S", "EPS", "EPSS", "S.A.", "S.A", "SA",
        "LTDA.", "LTDA", "S.A.S.", "S.A.S", "SAS",
        "DE SALUD", "ENTIDAD PROMOTORA DE SALUD",
        "DIR.", "DIRECCION", "GENERAL", "FUERZAS", "MILITAR", "MILITARES",
        ".", ",", "-", "_",
    ]:
        s = s.replace(term, " ")
    # Colapsar espacios
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _build_password(first_name: str, document_number: str) -> str:
    """Genera la contraseña: PrimerNombre + NumeroDocumento.

    Ejemplo: Santiago + 1027522598 = Santiago1027522598
    """
    # Qitar acentos del nombre para evitar problemas de teclado
    clean = _strip_accents(first_name).strip()
    return f"{clean}{document_number}"


def _split_name(full_name: str) -> tuple[str, str]:
    """Separa 'Santiago Pérez Gómez' en ('Santiago', 'Pérez Gómez').

    Asume formato: PrimerNombre [SegundoNombre] Apellidos...
    La contraseña usa solo el primer token (primer nombre).
    """
    parts = full_name.strip().split()
    if not parts:
        return ("", "")
    first_name = parts[0]
    last_name = " ".join(parts[1:]) if len(parts) > 1 else ""
    return (first_name, last_name)


def _parse_date(date_str: str):
    """Convierte '31/08/2005' → date(2005, 8, 31). Retorna None si falla."""
    if not date_str:
        return None
    for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y"):
        try:
            return datetime.strptime(date_str.strip(), fmt).date()
        except (ValueError, TypeError):
            continue
    return None


def _normalize_phone(phone: str) -> str:
    """Limpia un teléfono: deja solo dígitos."""
    if not phone:
        return ""
    digits = re.sub(r"\D", "", phone)
    return digits[:20] if digits else ""


# ──────────────────────────────────────────────
#  Lógica principal
# ──────────────────────────────────────────────

async def get_engine():
    return create_async_engine(settings.effective_database_url)


async def _load_role_map(db: AsyncSession) -> dict:
    """Carga todos los roles en un dict {nombre_lower: uuid}."""
    result = await db.execute(select(text("id, name, slug, area, hierarchy_level")).select_from(text("roles")))
    # Usar SQL crudo para no depender del modelo ORM aquí
    result = await db.execute(text("SELECT id, name, slug FROM roles"))
    role_map = {}
    for row in result:
        role_map[row.name.strip().upper()] = row.id
        # También mapear variantes comunes
    return role_map


def _match_role(role_name: str, role_map: dict) -> uuid.UUID | None:
    """Hace matching fuzzy del rol del operador contra los roles del sistema.

    Datos de entrada tienen: 'OPERADOR LOGISTICO', 'Brigadistas de Emergencias'
    Sistema tiene: 'Operador Logístico', 'Brigadista de Emergencias'
    """
    if not role_name:
        return None
    norm = _strip_accents(role_name).upper().strip()
    # Singular/plural: quitar 'S' final para matching flexible
    norm_singular = re.sub(r"S$", "", norm)

    # Match directo
    for key, rid in role_map.items():
        key_norm = _strip_accents(key).upper().strip()
        if key_norm == norm or key_norm == norm_singular:
            return rid

    # Match parcial (contains)
    for key, rid in role_map.items():
        key_norm = _strip_accents(key).upper().strip()
        if norm in key_norm or key_norm in norm:
            return rid
        # Palabras clave
        if "BRIGADISTA" in norm and "BRIGADISTA" in key_norm:
            return rid
        if "OPERADOR" in norm and "LOGIST" in norm and "LOGIST" in key_norm:
            return rid

    return None


async def _load_eps_map(db: AsyncSession) -> list:
    """Carga todas las EPS como lista de (id, normalized_name, raw_name)."""
    result = await db.execute(text("SELECT id, name FROM eps WHERE is_active = true"))
    eps_list = []
    for row in result:
        eps_list.append((row.id, _normalize_eps(row.name), row.name))
    return eps_list


def _match_eps(eps_name: str, eps_list: list) -> uuid.UUID | None:
    """Hace matching fuzzy del nombre de EPS."""
    if not eps_name:
        return None
    norm = _normalize_eps(eps_name)

    # Match exacto normalizado
    for eid, ename_norm, _ in eps_list:
        if ename_norm == norm:
            return eid

    # Match parcial: la EPS del sistema está contenida en el input (o viceversa)
    for eid, ename_norm, _ in eps_list:
        if not ename_norm or not norm:
            continue
        if ename_norm in norm or norm in ename_norm:
            return eid

    # Matching por palabras clave
    keywords_map = {
        "SURA": "SURA",
        "SANITAS": "SANITAS",
        "NUEVA": "NUEVA",
        "COMPENSAR": "COMPENSAR",
        "FAMISANAR": "FAMISANAR",
        "SALUD TOTAL": "SALUD TOTAL",
        "CAPITAL SALUD": "CAPITAL SALUD",
        "SOS": "SERVICIO OCCIDENTAL",
    }
    norm_upper = norm.upper()
    for kw, eps_kw in keywords_map.items():
        if kw in norm_upper:
            for eid, ename_norm, _ in eps_list:
                if eps_kw.upper() in ename_norm.upper():
                    return eid

    return None


async def _get_or_create_role(db: AsyncSession, role_name: str) -> uuid.UUID:
    """Obtiene o crea un rol por nombre. Para roles no estándar del seed."""
    norm_name = role_name.strip().title()
    slug = _strip_accents(norm_name).lower().replace(" ", "_")[:50]

    result = await db.execute(text("SELECT id FROM roles WHERE slug = :slug"), {"slug": slug})
    row = result.first()
    if row:
        return row.id

    await db.execute(text("""
        INSERT INTO roles (id, name, slug, description, hierarchy_level, is_active)
        VALUES (gen_random_uuid(), :name, :slug, 'Rol importado', 3, true)
    """), {"name": norm_name, "slug": slug})
    return None  # Se resuelve después del INSERT


async def import_operators(
    db: AsyncSession,
    operators: list[dict],
    event_id: str | None = None,
    assignment_status: str = "confirmed",
    dry_run: bool = False,
):
    """Importa operadores. Retorna estadísticas."""
    print("\n" + "=" * 60)
    print(f"  IMPORTADOR DE OPERADORES")
    print(f"  Total a procesar: {len(operators)}")
    if event_id:
        print(f"  Evento: {event_id} (status='{assignment_status}')")
    if dry_run:
        print(f"  ⚠️  DRY RUN — no se guardará nada")
    print("=" * 60 + "\n")

    # Pre-cargar catálogos
    role_map = await _load_role_map(db)
    print(f"📋 {len(role_map)} roles disponibles en el sistema")

    eps_list = await _load_eps_map(db)
    print(f"🏥 {len(eps_list)} EPS disponibles en el sistema\n")

    created = 0
    skipped_existing = 0
    errors = 0
    eps_matched = 0
    eps_unmatched_list = []

    for i, op_data in enumerate(operators, 1):
        full_name = op_data.get("full_name", "").strip()
        doc = op_data.get("document_number", "").strip()

        if not full_name or not doc:
            print(f"  [{i}] ❌ Sin nombre o documento — saltando")
            errors += 1
            continue

        first_name, last_name = _split_name(full_name)
        password = _build_password(first_name, doc)

        # --- Verificar si ya existe (por document_number) ---
        existing = await db.execute(
            text("SELECT id FROM users WHERE document_number = :doc AND is_active = true"),
            {"doc": doc},
        )
        if existing.first():
            print(f"  [{i}] ⏭️  {first_name} {last_name} ({doc}) — ya existe, saltando")
            skipped_existing += 1
            # Si hay evento, asignar igual
            if event_id:
                user_id = existing.first().id
                await _assign_to_event(db, user_id, event_id, op_data, role_map, assignment_status, dry_run)
            continue

        # --- Match EPS ---
        eps_name = op_data.get("eps_name", "")
        eps_id = _match_eps(eps_name, eps_list)
        if eps_id:
            eps_matched += 1
        elif eps_name:
            eps_unmatched_list.append(f"{full_name}: '{eps_name}'")

        # --- Match Role ---
        role_name = op_data.get("role_name", "")
        role_id = _match_role(role_name, role_map)

        # Parsear campos
        birth_date = _parse_date(op_data.get("birth_date", ""))
        phone = _normalize_phone(op_data.get("phone", ""))
        address = op_data.get("address", "").strip()
        gender = op_data.get("gender", "").strip()
        emergency_name = op_data.get("emergency_contact_name", "").strip()
        emergency_phone = _normalize_phone(op_data.get("emergency_contact_phone", ""))
        email = f"{doc}@operador.temp"

        if dry_run:
            eps_status = "✅" if eps_id else "❌"
            role_status = "✅" if role_id else "⚠️"
            print(f"  [{i}] DRY: {first_name} {last_name} ({doc}) | EPS:{eps_status} Rol:{role_status} | pw={password}")
            created += 1
            continue

        # --- Crear User ---
        try:
            pw_hash = hash_password(password)
            user_result = await db.execute(text("""
                INSERT INTO users (
                    id, email, password_hash, first_name, last_name,
                    phone, document_type, document_number, user_type,
                    role_id, is_verified, is_approved, is_active
                ) VALUES (
                    gen_random_uuid(), :email, :pw, :first_name, :last_name,
                    :phone, 'CC', :doc, 'operator',
                    :role_id, true, true, true
                )
                RETURNING id
            """), {
                "email": email, "pw": pw_hash,
                "first_name": first_name, "last_name": last_name,
                "phone": phone or None, "doc": doc,
                "role_id": role_id,
            })
            user_id = user_result.scalar()
        except Exception as exc:
            print(f"  [{i}] ❌ Error creando user {doc}: {exc}")
            await db.rollback()
            errors += 1
            continue

        # --- Crear Operator profile ---
        # experience_roles: JSON con el role_id para que el admin agrupe correctamente
        import json as _json
        experience_roles_json = _json.dumps([str(role_id)]) if role_id else None

        try:
            await db.execute(text("""
                INSERT INTO operators (
                    id, user_id, eps_id, birth_date, gender, address,
                    emergency_contact_name, emergency_contact_phone,
                    whatsapp, background_check_status, total_events, is_active,
                    experience_roles, has_protocol_experience, event_size_experience
                ) VALUES (
                    gen_random_uuid(), :user_id, :eps_id, :birth_date, :gender, :address,
                    :emergency_name, :emergency_phone,
                    :whatsapp, 'pending', 0, true,
                    :experience_roles, true, '100'
                )
            """), {
                "user_id": user_id,
                "eps_id": eps_id,
                "birth_date": birth_date,
                "gender": gender or None,
                "address": address or None,
                "emergency_name": emergency_name or None,
                "emergency_phone": emergency_phone or None,
                "whatsapp": phone or None,
                "experience_roles": experience_roles_json,
            })
        except Exception as exc:
            print(f"  [{i}] ❌ Error creando operator profile {doc}: {exc}")
            await db.rollback()
            errors += 1
            continue

        eps_label = "✅" if eps_id else "❌"
        print(f"  [{i}] ✅ {first_name} {last_name} ({doc}) — creado | EPS:{eps_label} pw={password}")
        created += 1

        # --- Asignar a evento si se especificó ---
        if event_id:
            await _assign_to_event(db, user_id, event_id, op_data, role_map, assignment_status, dry_run, operator_created=True)

    # --- Commit final ---
    if not dry_run:
        await db.commit()

    # --- Resumen ---
    print("\n" + "=" * 60)
    print("  RESUMEN")
    print("=" * 60)
    print(f"  ✅ Creados:        {created}")
    print(f"  ⏭️  Ya existían:    {skipped_existing}")
    print(f"  ❌ Errores:        {errors}")
    print(f"  🏥 EPS matcheadas: {eps_matched}/{len(operators)}")
    if eps_unmatched_list:
        print(f"\n  ⚠️  EPS sin match ({len(eps_unmatched_list)}):")
        for e in eps_unmatched_list[:10]:
            print(f"     • {e}")
    print("=" * 60 + "\n")


async def _assign_to_event(
    db: AsyncSession,
    user_id: uuid.UUID,
    event_id: str,
    op_data: dict,
    role_map: dict,
    status: str,
    dry_run: bool,
    operator_created: bool = False,
):
    """Asigna un operador a un evento. Crea EventAssignment si no existe."""
    # Buscar el operator_id desde user_id
    result = await db.execute(
        text("SELECT id FROM operators WHERE user_id = :uid"),
        {"uid": user_id},
    )
    row = result.first()
    if not row:
        return
    operator_id = row.id

    # Verificar si ya está asignado
    existing = await db.execute(
        text("SELECT id FROM event_assignments WHERE event_id = :eid AND operator_id = :oid"),
        {"eid": event_id, "oid": operator_id},
    )
    if existing.first():
        return

    # Match role
    role_name = op_data.get("role_name", "")
    role_id = _match_role(role_name, role_map)

    if dry_run:
        return

    await db.execute(text("""
        INSERT INTO event_assignments (id, event_id, operator_id, role_id, status, confirmed_at, is_active, reminder_sent)
        VALUES (gen_random_uuid(), :eid, :oid, :rid, :status, NOW(), true, false)
        ON CONFLICT DO NOTHING
    """), {"eid": event_id, "oid": operator_id, "rid": role_id, "status": status})


# ──────────────────────────────────────────────
#  CLI entrypoint
# ──────────────────────────────────────────────

async def main():
    import argparse

    parser = argparse.ArgumentParser(description="Importador masivo de operadores")
    parser.add_argument("--file", default="scripts/data/operators_batch.json",
                        help="Ruta del JSON con los operadores")
    parser.add_argument("--event", default=None,
                        help="UUID del evento para asignar los operadores")
    parser.add_argument("--status", default="confirmed",
                        help="Status de asignación: confirmed, invited, standby")
    parser.add_argument("--dry-run", action="store_true",
                        help="Simular sin guardar nada")
    args = parser.parse_args()

    # Cargar JSON
    json_path = Path(args.file)
    if not json_path.is_absolute():
        # Resolver relativo al directorio backend/
        backend_dir = Path(__file__).resolve().parent.parent
        json_path = backend_dir / args.file

    if not json_path.exists():
        print(f"❌ No se encontró: {json_path}")
        sys.exit(1)

    with open(json_path, "r", encoding="utf-8") as f:
        operators = json.load(f)

    print(f"📂 Cargados {len(operators)} operadores desde {json_path.name}")

    engine = await get_engine()
    S = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with S() as db:
        await import_operators(
            db, operators,
            event_id=args.event,
            assignment_status=args.status,
            dry_run=args.dry_run,
        )
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())