"""Análisis temporal de duplicados en los archivos de datos.

Orden cronológico de importación:
    1. operators_batch.json      (batch 1)
    2. operators_batch2.json     (batch 2)
    3. operators_batch3.json     (batch 3)
    4. operators_batch4_raw.txt  (batch 4)
"""
import json
import re
from pathlib import Path
from collections import defaultdict

DATA_DIR = Path(__file__).parent / "scripts" / "data"
docs = defaultdict(list)  # document_number -> [(coordinator, source_file, role, order)]

ORDER = {
    "operators_batch.json": 1,
    "operators_batch2.json": 2,
    "operators_batch3.json": 3,
    "batch4_raw.txt": 4,
}

# 1. JSONs (orden cronológico)
for jf in ["operators_batch.json", "operators_batch2.json", "operators_batch3.json"]:
    path = DATA_DIR / jf
    if not path.exists():
        continue
    items = json.loads(path.read_text(encoding="utf-8"))
    for it in items:
        doc = it.get("document_number", "").strip()
        coord = it.get("coordinator", "").strip()
        role = it.get("role_name", "").strip()
        docs[doc].append((coord, jf, role, ORDER[jf]))

# 2. TXT raw
txt = DATA_DIR / "operators_batch4_raw.txt"
if txt.exists():
    content = txt.read_text(encoding="utf-8")
    blocks = re.split(r"-{10,}", content)
    for block in blocks:
        doc_m = re.search(r"NUMERO CEDULA:\s*(\S+)", block)
        coord_m = re.search(r"COORDINADOR QUE LO PROGRAMA:\s*(.+)", block)
        role_m = re.search(r"ROL ASIGNADO:\s*(.+)", block)
        if doc_m:
            doc = doc_m.group(1).strip()
            coord = coord_m.group(1).strip() if coord_m else ""
            role = role_m.group(1).strip() if role_m else ""
            docs[doc].append((coord, "batch4_raw.txt", role, ORDER["batch4_raw.txt"]))

# Reportar
dups = {d: entries for d, entries in docs.items() if len(entries) > 1}
lines = []
lines.append(f"Total cedulas unicas: {len(docs)}")
lines.append(f"Cedulas duplicadas: {len(dups)}")
lines.append("")

# Listar coordinadores únicos encontrados
all_coords = set()
for entries in docs.values():
    for e in entries:
        if e[0]:
            all_coords.add(e[0])
lines.append(f"Coordinadores unicos ({len(all_coords)}): {sorted(all_coords)}")
lines.append("")

for doc, entries in sorted(dups.items()):
    # Ordenar por orden de batch
    entries_sorted = sorted(entries, key=lambda x: x[3])
    coords = set(e[0] for e in entries)
    same_coord = len(coords) == 1
    lines.append(f"Doc {doc}:")
    for coord, src, role, order in entries_sorted:
        lines.append(f"   [{src}] coord={coord!r} role={role!r}")
    if not same_coord:
        # Mostrar el coordinador ganador (último)
        winner = entries_sorted[-1][0]
        lines.append(f"   *** CONFLICTO -> GANA: {winner!r} (ultima fuente)")
    lines.append("")

out_path = Path(__file__).parent / "_dups_report.txt"
out_path.write_text("\n".join(lines), encoding="utf-8")
print(f"OK -> {out_path}")