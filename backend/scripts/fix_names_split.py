"""Corrige usuarios cuyo nombre quedó mal dividido entre first_name y last_name.

PROBLEMA:
    Al importar desde Excel, algunos operadores quedaron con el segundo nombre
    mezclado en los apellidos. Ejemplo:
        Actual:    first_name='Ronald'   last_name='Santiago Poveda Sarmiento'
        Correcto:  first_name='Ronald Santiago'  last_name='Poveda Sarmiento'

SOLUCIÓN:
    Detecta el patrón sospechoso (1 palabra en first_name + 3 palabras en
    last_name) y mueve la PRIMERA palabra de last_name al final de first_name.

MODO SEGURO (DRY-RUN por defecto):
    El script NO modifica nada a menos que se pase --apply.
    Primero muestra la tabla de candidatos para revisión manual.

USO:
    # Dry-run (solo lectura, muestra qué cambiaría):
    python -m scripts.fix_names_split

    # Dry-run filtrando por evento (solo operadores asignados a ese evento):
    python -m scripts.fix_names_split --event-id <UUID>

    # Dry-run filtrando por documento específico:
    python -m scripts.fix_names_split --doc 1027522598

    # Aplicar cambios (después de revisar el dry-run):
    python -m scripts.fix_names_split --apply

    # Aplicar cambios para un evento específico:
    python -m scripts.fix_names_split --event-id <UUID> --apply

NOTAS:
    - Solo modifica registros de operadores (user_type='operator').
    - No elimina usuarios ni cambia FKs, email, ni contraseña.
    - Solo mueve UNA palabra de last_name -> first_name.
    - Omite casos ambiguos (1+4 palabras, apellidos compuestos como 'De la Cruz')
      reportándolos por separado para revisión manual.
"""
import argparse
import asyncio
import os
import re
import sys
import unicodedata
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings


# ──────────────────────────────────────────────
#  Heurística de detección
# ──────────────────────────────────────────────

# Apellidos compuestos españoles que NO deben romperse. Si la primera palabra
# del last_name es uno de estos, NO se mueve (es parte legítima del apellido).
# Se comparan sin acentos y en UPPER.
COMPOUND_LASTNAME_TOKENS = {
    "DE", "DEL", "DE LA", "LA", "LAS", "LOS", "DA", "DAS", "DO", "DOS",
    "Y", "MAC", "MC", "O", "SAN", "SANTA",
}

# Placeholders que indican que NO hay segundo nombre (dejar el registro tal cual).
# Si la primera palabra del last_name es uno de estos, no se mueve (iría a review).
PLACEHOLDER_TOKENS = {
    "N/A", "NA", "NINGUNO", "NINGUNA", "NO", "NADA", "NULL", "S/N", "SN",
    ".", "-", "--", "...", "X", "XX", "XXX", "SIN", "SIN NOMBRE",
}


def _strip_accents(s: str) -> str:
    if not s:
        return ""
    nfkd = unicodedata.normalize("NFKD", s)
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def _classify(first_name: str, last_name: str) -> str:
    """Clasifica el patrón de un usuario.

    Returns:
        'fix_1_plus_3'  : 1 nombre + 3 apellidos -> seguro de corregir (caso del reporte)
        'review_1_plus_4_plus' : 1 nombre + 4+ apellidos -> requiere revisión manual
        'ok'            : patrón normal (no se toca)
    """
    fn = (first_name or "").strip()
    ln = (last_name or "").strip()
    fn_words = fn.split()
    ln_words = ln.split()

    if len(fn_words) == 1 and len(ln_words) == 3:
        # Caso clásico: "Ronald" + "Santiago Poveda Sarmiento"
        first_token_norm = _strip_accents(ln_words[0]).upper()

        # 1) Si la primera palabra del apellido es un token compuesto legítimo
        #    (ej: "De la Cruz"), no se toca.
        if first_token_norm in COMPOUND_LASTNAME_TOKENS:
            return "ok"

        # 2) Si la primera palabra del apellido es un placeholder (N/A, Ninguno, etc.),
        #    NO se mueve y se envía a revisión manual (no hay segundo nombre real).
        if first_token_norm in PLACEHOLDER_TOKENS:
            return "review_placeholder"

        # 3) Si mover la palabra generaría un duplicado
        #    (ej: "Lucely" + "Lucely Romero Martinez"), no se mueve -> revisión.
        fn_norm = _strip_accents(fn_words[0]).upper()
        if fn_norm == first_token_norm:
            return "review_duplicate"

        return "fix_1_plus_3"

    if len(fn_words) == 1 and len(ln_words) >= 4:
        return "review_1_plus_4_plus"

    return "ok"


def _propose_fix(first_name: str, last_name: str) -> tuple[str, str]:
    """Propone la corrección para el patrón 1+3.

    Mueve la primera palabra de last_name al final de first_name.
    """
    fn_words = (first_name or "").strip().split()
    ln_words = (last_name or "").strip().split()
    new_first = " ".join(fn_words + [ln_words[0]])
    new_last = " ".join(ln_words[1:])
    return new_first, new_last


# ──────────────────────────────────────────────
#  Consulta a la BD
# ──────────────────────────────────────────────

async def _fetch_candidates(db, event_id=None, doc=None):
    """Trae usuarios operadores que pueden estar mal divididos.

    Retorna lista de dicts con: id, document_number, first_name, last_name,
    email, event_id (si aplica).
    """
    params = {}
    sql = """
        SELECT u.id, u.document_number, u.first_name, u.last_name, u.email
    """
    if event_id:
        sql += ", ea.event_id"
        sql += """
            FROM users u
            JOIN operators o ON o.user_id = u.id
            JOIN event_assignments ea ON ea.operator_id = o.id
            WHERE u.user_type = 'operator'
              AND ea.event_id = :event_id
        """
        params["event_id"] = str(event_id)
    else:
        sql += """
            FROM users u
            WHERE u.user_type = 'operator'
        """
    if doc:
        sql += " AND u.document_number = :doc"
        params["doc"] = str(doc)
    sql += " ORDER BY u.first_name, u.last_name"

    result = await db.execute(text(sql), params)
    rows = []
    for r in result:
        rows.append({
            "id": str(r.id),
            "document_number": r.document_number,
            "first_name": r.first_name,
            "last_name": r.last_name,
            "email": r.email,
        })
    return rows


async def _apply_fix(db, user_id: str, new_first: str, new_last: str):
    """Aplica el UPDATE a un usuario (sin tocar nada más)."""
    await db.execute(text("""
        UPDATE users
        SET first_name = :fn, last_name = :ln, updated_at = NOW()
        WHERE id = :uid
    """), {
        "uid": user_id,
        "fn": new_first[:100],
        "ln": new_last[:100],
    })


# ──────────────────────────────────────────────
#  CLI
# ──────────────────────────────────────────────

async def main():
    parser = argparse.ArgumentParser(
        description="Corrige first_name/last_name mal divididos (dry-run por defecto)."
    )
    parser.add_argument("--apply", action="store_true",
                        help="Aplica los cambios (sin esto, solo muestra el dry-run).")
    parser.add_argument("--event-id", default=None,
                        help="Filtra por evento (solo operadores asignados a ese evento).")
    parser.add_argument("--doc", default=None,
                        help="Filtra por número de documento específico.")
    args = parser.parse_args()

    engine = create_async_engine(settings.effective_database_url)
    S = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    print("=" * 80)
    print(" CORRECCIÓN DE NOMBRES MAL DIVIDIDOS (first_name / last_name)")
    print("=" * 80)
    print(f" Modo          : {'APLICAR CAMBIOS' if args.apply else 'DRY-RUN (solo lectura)'}")
    if args.event_id:
        print(f" Evento        : {args.event_id}")
    if args.doc:
        print(f" Documento     : {args.doc}")
    print(f" BD            : {settings.effective_database_url.split('@')[-1] if '@' in settings.effective_database_url else '(config)'}")
    print(f" Timestamp     : {datetime.now().isoformat(timespec='seconds')}")
    print("=" * 80)

    async with S() as db:
        users = await _fetch_candidates(db, event_id=args.event_id, doc=args.doc)
        print(f"\nOperadores analizados: {len(users)}\n")

        to_fix = []          # patrón 1+3 (seguro de corregir)
        review_1_plus_4 = [] # 1 nombre + 4+ apellidos (ambiguo)
        review_placeholder = []  # la 2ª palabra es placeholder (N/A, Ninguno, etc.)
        review_duplicate = []    # mover crearía un duplicado (mismo nombre 2x)

        for u in users:
            kind = _classify(u["first_name"], u["last_name"])
            if kind == "fix_1_plus_3":
                new_first, new_last = _propose_fix(u["first_name"], u["last_name"])
                u["new_first_name"] = new_first
                u["new_last_name"] = new_last
                to_fix.append(u)
            elif kind == "review_1_plus_4_plus":
                review_1_plus_4.append(u)
            elif kind == "review_placeholder":
                review_placeholder.append(u)
            elif kind == "review_duplicate":
                review_duplicate.append(u)

        # --- Mostrar candidatos a corregir (1+3) ---
        if to_fix:
            print("-" * 80)
            print(f" CANDIDATOS A CORREGIR AUTOMÁTICAMENTE ({len(to_fix)}):")
            print("  Patrón detectado: 1 nombre + 3 apellidos -> 2 nombres + 2 apellidos")
            print("-" * 80)
            print(f"{'#':>3}  {'Documento':<14}  {'ANTES (first | last)':<50}  {'DESPUÉS':<40}")
            for i, u in enumerate(to_fix, 1):
                antes = f"{u['first_name']} | {u['last_name']}"
                despues = f"{u['new_first_name']} | {u['new_last_name']}"
                print(f"{i:>3}  {u['document_number'] or '-':<14}  {antes[:50]:<50}  {despues[:40]:<40}")
        else:
            print("\n[OK] No se encontraron candidatos con el patron 1+3.")

        # --- Mostrar casos para revision manual: placeholders ---
        if review_placeholder:
            print("\n" + "-" * 80)
            print(f" [REVISAR] PLACEHOLDER COMO SEGUNDO NOMBRE ({len(review_placeholder)}):")
            print("  La 2a palabra del apellido es N/A, Ninguno, No, etc. -> NO se mueve")
            print("-" * 80)
            for u in review_placeholder:
                print(f"   {u['document_number'] or '-':<14}  {u['first_name']} | {u['last_name']}")

        # --- Mostrar casos para revision manual: duplicados ---
        if review_duplicate:
            print("\n" + "-" * 80)
            print(f" [REVISAR] MOVER GENERARIA DUPLICADO ({len(review_duplicate)}):")
            print("  La 2a palabra del apellido es igual al primer nombre -> NO se mueve")
            print("-" * 80)
            for u in review_duplicate:
                print(f"   {u['document_number'] or '-':<14}  {u['first_name']} | {u['last_name']}")

        # --- Mostrar casos para revision manual: 1+4+ ---
        if review_1_plus_4:
            print("\n" + "-" * 80)
            print(f" [REVISAR] 1 NOMBRE + 4+ APELLIDOS ({len(review_1_plus_4)}):")
            print("  Patron ambiguo - no se corrige automaticamente")
            print("-" * 80)
            for u in review_1_plus_4:
                print(f"   {u['document_number'] or '-':<14}  {u['first_name']} | {u['last_name']}")

        # --- Resumen ---
        total_review = len(review_placeholder) + len(review_duplicate) + len(review_1_plus_4)
        print("\n" + "=" * 80)
        print(f" RESUMEN: {len(to_fix)} a corregir | {total_review} para revision manual | {len(users) - len(to_fix) - total_review} OK")
        print("=" * 80)

        # --- Aplicar si se solicito ---
        if args.apply and to_fix:
            print("\n" + "=" * 80)
            confirm = input(f"Aplicar {len(to_fix)} correcciones? Escriba 'SI' para confirmar: ")
            if confirm.strip().upper() != "SI":
                print("[X] Cancelado por el usuario. No se aplicaron cambios.")
                await engine.dispose()
                return

            applied = 0
            for u in to_fix:
                await _apply_fix(db, u["id"], u["new_first_name"], u["new_last_name"])
                applied += 1
            await db.commit()
            print(f"\n[OK] {applied} usuarios corregidos correctamente.")
        elif args.apply and not to_fix:
            print("\n[i] No hay cambios que aplicar.")
        else:
            if to_fix:
                print("\n" + "=" * 80)
                print("[i] DRY-RUN completado. Para aplicar los cambios, vuelva a ejecutar con --apply")
                print("    Ejemplo: python -m scripts.fix_names_split --apply")
                if args.event_id:
                    print(f"             python -m scripts.fix_names_split --event-id {args.event_id} --apply")
            print("\n[i] No se modifico ningun registro.")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())