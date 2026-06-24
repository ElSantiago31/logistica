#!/usr/bin/env python
"""Corrige el rol de los universitarios importados que quedaron sin role_id.

Causa típica: la importación se ejecutó antes de que el rol 'Universitario'
existiera en la BD (timing del seed), por lo que el matching de roles falló
y todos quedaron con role_id = NULL.

Uso:
    python -m scripts.fix_universitarios_roles          # corrige por cédulas del JSON
    python -m scripts.fix_universitarios_roles --dry-run # simular
    python -m scripts.fix_universitarios_roles --file scripts/data/universitarios.json
"""
import asyncio
import json
import os
import sys
import uuid
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


async def get_engine():
    return create_async_engine(settings.effective_database_url)


async def ensure_universitario_role(db: AsyncSession) -> uuid.UUID:
    """Garantiza que el rol 'Universitario' exista. Retorna su ID."""
    result = await db.execute(
        text("SELECT id FROM roles WHERE slug = 'universitario'")
    )
    row = result.first()
    if row:
        print(f"✅ Rol 'Universitario' ya existe (id={row.id})")
        return row.id

    # Crear el rol si no existe
    await db.execute(text("""
        INSERT INTO roles (id, name, slug, description, hierarchy_level, area, is_active)
        VALUES (gen_random_uuid(), 'Universitario', 'universitario',
                'Personal universitario cercano a artistas', 3, 'Seguridad', true)
    """))
    await db.commit()
    print("✅ Rol 'Universitario' creado")

    result = await db.execute(
        text("SELECT id FROM roles WHERE slug = 'universitario'")
    )
    return result.first().id


async def fix_roles(db: AsyncSession, json_path: Path, dry_run: bool = False):
    """Asigna el rol a los universitarios listados en el JSON (por cédula)."""
    role_id = await ensure_universitario_role(db)

    with open(json_path, "r", encoding="utf-8") as f:
        operators = json.load(f)

    print(f"\n📂 {len(operators)} universitarios en {json_path.name}")
    print(f"🎯 Rol a asignar: Universitario (id={role_id})\n")

    updated = 0
    not_found = 0
    already_ok = 0
    not_found_docs = []

    for i, op in enumerate(operators, 1):
        doc = op.get("document_number", "").strip()
        full_name = op.get("full_name", "").strip()
        if not doc:
            continue

        result = await db.execute(
            text("SELECT id, role_id FROM users WHERE document_number = :doc"),
            {"doc": doc},
        )
        row = result.first()

        if not row:
            not_found += 1
            not_found_docs.append(f"{full_name} ({doc})")
            continue

        if str(row.role_id) == str(role_id):
            already_ok += 1
            continue

        if dry_run:
            print(f"  [{i}] DRY: asignaría rol a {full_name} ({doc})")
            updated += 1
            continue

        await db.execute(
            text("UPDATE users SET role_id = :rid WHERE id = :uid"),
            {"rid": role_id, "uid": row.id},
        )
        print(f"  [{i}] ✅ {full_name} ({doc}) — rol asignado")
        updated += 1

    if not dry_run:
        await db.commit()

    # Resumen
    print("\n" + "=" * 60)
    print("  RESUMEN")
    print("=" * 60)
    print(f"  ✅ Actualizados:    {updated}")
    print(f"  ⏭️  Ya tenían rol:   {already_ok}")
    print(f"  ❌ No encontrados:  {not_found}")
    if not_found_docs:
        print(f"\n  ⚠️  Usuarios no encontrados en la BD ({len(not_found_docs)}):")
        for nf in not_found_docs[:15]:
            print(f"     • {nf}")
        if len(not_found_docs) > 15:
            print(f"     ... y {len(not_found_docs) - 15} más")
    print("=" * 60 + "\n")


async def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Corrige el rol de los universitarios importados"
    )
    parser.add_argument(
        "--file",
        default="scripts/data/universitarios.json",
        help="Ruta del JSON con los universitarios",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Simular sin guardar nada",
    )
    args = parser.parse_args()

    json_path = Path(args.file)
    if not json_path.is_absolute():
        backend_dir = Path(__file__).resolve().parent.parent
        json_path = backend_dir / args.file

    if not json_path.exists():
        print(f"❌ No se encontró: {json_path}")
        sys.exit(1)

    engine = await get_engine()
    S = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with S() as db:
        await fix_roles(db, json_path, dry_run=args.dry_run)
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())