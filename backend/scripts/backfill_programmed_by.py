#!/usr/bin/env python
"""Backfill de programmed_by en event_assignments.

PROBLEMA:
    Los operadores fueron importados con un campo "coordinator" (nombre del
    coordinador que los programó/reclutó), pero ese dato NO llegó a la tabla
    event_assignments. El check-in solo muestra el coordinador por área del
    rol, no quién realmente programó al operador.

SOLUCIÓN:
    1. Lee los archivos de datos (JSON + TXT) en orden cronológico.
    2. Construye un mapa {document_number: programmed_by} aplicando
       "última fuente gana" para resolver duplicados/conflictos.
    3. Recorre todas las event_assignments, hace match por cédula del
       operador (vía users.document_number) y setea programmed_by.

USO:
    python -m scripts.backfill_programmed_by             # aplicar
    python -m scripts.backfill_programmed_by --dry-run   # simular
    python -m scripts.backfill_programmed_by --only-missing  # solo NULLs
"""
import asyncio
import json
import os
import re
import sys
from collections import defaultdict
from pathlib import Path

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

DATA_DIR = Path(__file__).parent / "data"

# Orden cronológico de importación (las últimas sobrescriben)
SOURCES = [
    ("operators_batch.json", 1),
    ("operators_batch2.json", 2),
    ("operators_batch3.json", 3),
    ("operators_batch4_raw.txt", 4),
]


def build_programmed_by_map():
    """Construye {document_number: programmed_by} con 'última fuente gana'."""
    docs = {}  # doc -> (programmed_by, order)

    # 1. JSONs
    for fname, order in SOURCES:
        if not fname.endswith(".json"):
            continue
        path = DATA_DIR / fname
        if not path.exists():
            continue
        items = json.loads(path.read_text(encoding="utf-8"))
        for it in items:
            doc = (it.get("document_number") or "").strip()
            coord = (it.get("coordinator") or "").strip()
            if doc and coord:
                docs[doc] = (coord, order)

    # 2. TXT raw (batch4)
    txt_name = "operators_batch4_raw.txt"
    txt_path = DATA_DIR / txt_name
    if txt_path.exists():
        order = dict(SOURCES)[txt_name]
        content = txt_path.read_text(encoding="utf-8")
        blocks = re.split(r"-{10,}", content)
        for block in blocks:
            doc_m = re.search(r"NUMERO CEDULA:\s*(\S+)", block)
            coord_m = re.search(r"COORDINADOR QUE LO PROGRAMA:\s*(.+)", block)
            if doc_m and coord_m:
                doc = doc_m.group(1).strip()
                coord = coord_m.group(1).strip()
                if doc and coord:
                    docs[doc] = (coord, order)

    # Resolver: dejar solo el programmed_by (ya quedo el último por order)
    return {doc: coord for doc, (coord, _order) in docs.items()}


async def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Backfill de programmed_by en event_assignments"
    )
    parser.add_argument("--dry-run", action="store_true", help="Simular sin guardar")
    parser.add_argument(
        "--only-missing",
        action="store_true",
        help="Solo asignaciones con programmed_by NULL",
    )
    args = parser.parse_args()

    print("\n" + "=" * 60)
    print("  BACKFILL DE programmed_by")
    print("=" * 60)

    # 1. Construir el mapa
    prog_map = build_programmed_by_map()
    print(f"  📊 Coordinadores extraídos de archivos: {len(prog_map)}")

    if not prog_map:
        print("  ❌ No se encontraron datos. Verifica backend/scripts/data/")
        return

    # 2. Conectar a la BD
    engine = create_async_engine(settings.effective_database_url)
    S = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with S() as db:
        where_clause = ""
        if args.only_missing:
            where_clause = "AND ea.programmed_by IS NULL"

        # Contar asignaciones totales
        count_result = await db.execute(text(f"""
            SELECT COUNT(*) FROM event_assignments ea
            JOIN operators o ON ea.operator_id = o.id
            JOIN users u ON o.user_id = u.id
            WHERE u.document_number IS NOT NULL
            {where_clause}
        """))
        total = count_result.scalar() or 0
        print(f"  📋 Asignaciones a procesar: {total}")
        if args.dry_run:
            print("  ⚠️  DRY RUN — no se guardará nada")
        print()

        # Traer asignaciones con cédula
        result = await db.execute(text(f"""
            SELECT ea.id, u.document_number, u.first_name, u.last_name,
                   ea.programmed_by
            FROM event_assignments ea
            JOIN operators o ON ea.operator_id = o.id
            JOIN users u ON o.user_id = u.id
            WHERE u.document_number IS NOT NULL
            {where_clause}
        """))
        rows = result.fetchall()

        updated = 0
        skipped = 0
        not_found = 0
        conflicts = []

        for row in rows:
            doc = (row.document_number or "").strip()
            new_coord = prog_map.get(doc)
            if not new_coord:
                not_found += 1
                continue
            # Si ya tiene uno igual, saltar
            if row.programmed_by and row.programmed_by == new_coord:
                skipped += 1
                continue
            # Si ya tiene uno distinto, registrar conflicto pero sobrescribir
            if row.programmed_by and row.programmed_by != new_coord:
                conflicts.append({
                    "name": f"{row.first_name} {row.last_name}",
                    "doc": doc,
                    "old": row.programmed_by,
                    "new": new_coord,
                })

            if not args.dry_run:
                await db.execute(
                    text("UPDATE event_assignments SET programmed_by = :pb WHERE id = :aid"),
                    {"pb": new_coord, "aid": row.id},
                )
            updated += 1

        if not args.dry_run and updated > 0:
            await db.commit()

        # Resumen
        print("=" * 60)
        print("  RESUMEN")
        print("=" * 60)
        print(f"  ✅ Actualizados:     {updated}")
        print(f"  ⏭️  Sin cambios:      {skipped}")
        print(f"  ❓ Sin coordinador:  {not_found}")
        print(f"  ⚠️  Conflictos:       {len(conflicts)}")
        print("=" * 60 + "\n")

        if conflicts:
            print("  Conflictos resueltos (última fuente gana):")
            for c in conflicts[:20]:
                print(f"    {c['name']} ({c['doc']}): '{c['old']}' -> '{c['new']}'")
            if len(conflicts) > 20:
                print(f"    ... y {len(conflicts) - 20} más")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())