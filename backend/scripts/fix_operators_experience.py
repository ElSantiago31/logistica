#!/usr/bin/env python
"""Backfill de experience_roles para operadores importados.

PROBLEMA:
    El admin agrupa operadores por operators.experience_roles (JSON),
    NO por users.role_id. Los operadores importados quedaron con
    experience_roles = NULL, por lo que aparecen en "Sin experiencia".

SOLUCIÓN:
    Este script copia el role_id de users -> operators.experience_roles
    y marca has_protocol_experience=true, event_size_experience='100'.

    Así cada operador queda agrupado bajo su rol en el dashboard del admin.

USO:
    python -m scripts.fix_operators_experience             # corregir todos
    python -m scripts.fix_operators_experience --dry-run   # simular
    python -m scripts.fix_operators_experience --only-missing  # solo los que no tienen
"""
import asyncio
import json
import os
import sys

# Forzar UTF-8 en stdout/stderr (Windows usa cp1252 por defecto)
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except (AttributeError, Exception):
    pass

# Asegurar que backend/ esté en sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

from app.config import settings


async def get_engine():
    return create_async_engine(settings.effective_database_url)


async def fix_operators(db: AsyncSession, dry_run: bool = False, only_missing: bool = False):
    """Sincroniza experience_roles con role_id para todos los operadores.

    Args:
        db: Sesión de BD.
        dry_run: Si True, solo muestra qué haría sin guardar.
        only_missing: Si True, solo corrige los que tienen experience_roles NULL.
    """
    print("\n" + "=" * 60)
    print("  BACKFILL DE experience_roles")
    print("=" * 60)

    # Contar operadores que necesitan fix
    where_clause = ""
    if only_missing:
        where_clause = "AND (o.experience_roles IS NULL OR o.experience_roles = '[]' OR o.experience_roles = '')"

    count_result = await db.execute(text(f"""
        SELECT COUNT(*) as total
        FROM operators o
        JOIN users u ON o.user_id = u.id
        WHERE u.user_type = 'operator'
          AND u.is_active = true
          AND u.role_id IS NOT NULL
          {where_clause}
    """))
    total_to_fix = count_result.scalar() or 0

    # Contar operadores sin role_id
    no_role_result = await db.execute(text("""
        SELECT COUNT(*) as total
        FROM operators o
        JOIN users u ON o.user_id = u.id
        WHERE u.user_type = 'operator'
          AND u.is_active = true
          AND u.role_id IS NULL
    """))
    total_no_role = no_role_result.scalar() or 0

    print(f"  📊 Operadores a corregir: {total_to_fix}")
    print(f"  ⚠️  Operadores sin role_id: {total_no_role}")
    if dry_run:
        print(f"  ⚠️  DRY RUN — no se guardará nada")
    print()

    if total_to_fix == 0:
        print("  ✅ No hay operadores para corregir. Todo está al día.")
        return

    # Traer los operadores a corregir con detalle
    result = await db.execute(text(f"""
        SELECT u.id, u.first_name, u.last_name, u.document_number,
               u.role_id, o.experience_roles
        FROM operators o
        JOIN users u ON o.user_id = u.id
        WHERE u.user_type = 'operator'
          AND u.is_active = true
          AND u.role_id IS NOT NULL
          {where_clause}
        ORDER BY u.first_name, u.last_name
    """))

    rows = result.fetchall()
    updated = 0
    skipped = 0

    for i, row in enumerate(rows, 1):
        role_id = str(row.role_id)
        full_name = f"{row.first_name} {row.last_name}"

        # Construir experience_roles JSON
        experience_roles_json = json.dumps([role_id])

        if dry_run:
            print(f"  [{i}] DRY: {full_name} ({row.document_number}) -> rol={role_id}")
            updated += 1
            continue

        # UPDATE directo
        await db.execute(text("""
            UPDATE operators
            SET experience_roles = :er_json,
                has_protocol_experience = COALESCE(has_protocol_experience, true),
                event_size_experience = COALESCE(NULLIF(event_size_experience, ''), '100')
            WHERE user_id = :uid
        """), {
            "er_json": experience_roles_json,
            "uid": row.id,
        })

        if i % 50 == 0:
            print(f"  ... {i} procesados ...")
        updated += 1

    if not dry_run:
        await db.commit()

    # Resumen
    print("\n" + "=" * 60)
    print("  RESUMEN")
    print("=" * 60)
    print(f"  ✅ Actualizados:      {updated}")
    print(f"  ⏭️  Saltados:          {skipped}")
    if total_no_role > 0:
        print(f"  ⚠️  Sin role_id:       {total_no_role} (necesitan rol asignado primero)")
    print("=" * 60 + "\n")

    # Verificación post-fix
    if not dry_run:
        verify = await db.execute(text("""
            SELECT COUNT(*) as total
            FROM operators o
            JOIN users u ON o.user_id = u.id
            WHERE u.user_type = 'operator'
              AND u.is_active = true
              AND u.role_id IS NOT NULL
              AND (o.experience_roles IS NULL OR o.experience_roles = '[]' OR o.experience_roles = '')
        """))
        remaining = verify.scalar() or 0
        if remaining == 0:
            print("  ✅ Verificación: todos los operadores con rol tienen experience_roles.")
        else:
            print(f"  ⚠️  Verificación: {remaining} operadores aún sin experience_roles.")


async def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Backfill de experience_roles para operadores importados"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Simular sin guardar nada",
    )
    parser.add_argument(
        "--only-missing",
        action="store_true",
        help="Solo corregir operadores con experience_roles vacío (no sobrescribir existentes)",
    )
    args = parser.parse_args()

    engine = await get_engine()
    S = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with S() as db:
        await fix_operators(db, dry_run=args.dry_run, only_missing=args.only_missing)
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())