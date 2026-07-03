#!/usr/bin/env python
"""Extracción de firmas de operadores desde la DB de producción.

Se ejecuta DENTRO del contenedor ``logistica_backend`` en el VPS:

    docker exec logistica_backend python -m scripts.extract_signatures

Lee las firmas (base64 PNG) de ``payroll_records.signature_data`` para un
evento concreto y las guarda como archivos PNG individuales en
``/tmp/firmas_evento/{cedula}.png``.

Después, desde el host del VPS, se copian fuera del contenedor con:

    docker cp logistica_backend:/tmp/firmas_evento ./firmas_evento

Y finalmente se descargan al PC local con ``scp``.
"""
import asyncio
import base64
import json
import logging
import re
import sys
from pathlib import Path

# Permite importar ``app.*`` cuando se corre como módulo dentro del contenedor
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")
logger = logging.getLogger("extract_signatures")

# --- Configuración ---------------------------------------------------------
EVENT_ID = "13e549bf-fe1b-4bb3-9887-5c48bf0a25c1"
OUTPUT_DIR = Path("/tmp/firmas_evento")
# ---------------------------------------------------------------------------

_CEDULA_RE = re.compile(r"\d+")


def _normalize_cedula(raw: str | None) -> str:
    """Normaliza una cédula dejando SOLO dígitos."""
    if not raw:
        return ""
    m = _CEDULA_RE.findall(str(raw))
    return "".join(m)


def _decode_signature(signature_data: str | None) -> bytes | None:
    """Decodifica base64 PNG/JPG de la firma a bytes crudos.

    Soporta tanto base64 puro como ``data:image/png;base64,XXXX``.
    """
    if not signature_data:
        return None
    try:
        raw = str(signature_data).strip()
        if "," in raw and raw.startswith("data:image"):
            raw = raw.split(",", 1)[1]
        return base64.b64decode(raw)
    except Exception as exc:
        logger.warning("No se pudo decodificar una firma: %s", exc)
        return None


async def main() -> int:
    # Importación tardía para no arrancar settings si falla algo simple
    from sqlalchemy import text
    from app.database import AsyncSessionLocal  # type: ignore

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    logger.info("Extrayendo firmas del evento %s → %s", EVENT_ID, OUTPUT_DIR)

    query = text(
        """
        SELECT u.document_number,
               u.first_name,
               u.last_name,
               pr.signature_data
        FROM payroll_records pr
        JOIN operators o ON o.id = pr.operator_id
        JOIN users u ON u.id = o.user_id
        WHERE pr.event_id = :event_id
          AND pr.signature_data IS NOT NULL
          AND pr.signature_data <> ''
        ORDER BY u.document_number
        """
    )

    extracted = 0
    skipped = 0
    mapping: dict[str, str] = []

    async with AsyncSessionLocal() as session:
        result = await session.execute(query, {"event_id": EVENT_ID})
        rows = result.all()

    logger.info("Filas con signature_data no vacío: %d", len(rows))

    for row in rows:
        doc_raw, first_name, last_name, signature_data = row
        full_name = f"{first_name or ''} {last_name or ''}".strip()
        cedula = _normalize_cedula(doc_raw)
        if not cedula:
            skipped += 1
            logger.warning("Fila sin cédula válida (doc=%r) — omitida", doc_raw)
            continue

        png = _decode_signature(signature_data)
        if not png:
            skipped += 1
            logger.warning("Firma no decodificable para cédula %s — omitida", cedula)
            continue

        out = OUTPUT_DIR / f"{cedula}.png"
        out.write_bytes(png)
        extracted += 1
        mapping.append({
            "cedula": cedula,
            "nombre": full_name or "",
            "archivo": out.name,
            "bytes": len(png),
        })

    # JSON de diagnóstico (también dentro del contenedor)
    (OUTPUT_DIR / "_firmas_evento.json").write_text(
        json.dumps(mapping, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    logger.info("=" * 50)
    logger.info("✅ Firmas extraídas: %d", extracted)
    logger.info("⚠️  Filas omitidas: %d", skipped)
    logger.info("📁 Carpeta: %s", OUTPUT_DIR)
    logger.info("=" * 50)
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))