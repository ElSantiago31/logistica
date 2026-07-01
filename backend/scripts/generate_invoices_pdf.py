#!/usr/bin/env python
"""Genera un ZIP con todas las facturas PDF de un evento.

Filtro: status='paid' AND signature_data IS NOT NULL.

USO:
    python -m scripts.generate_invoices_pdf --event-id <UUID>
    python -m scripts.generate_invoices_pdf --event-id <UUID> --output ./recibos.zip
    python -m scripts.generate_invoices_pdf --event-id <UUID> --output-dir ./recibos
"""
import argparse
import asyncio
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
from app.services.invoice_pdf import generate_invoices_zip, generate_invoice_pdf


async def get_engine():
    return create_async_engine(settings.effective_database_url)


async def fetch_invoices(db: AsyncSession, event_id: str) -> tuple[list[dict], str]:
    """Consulta las facturas pagadas con firma del evento.

    Returns:
        (invoices_data, event_name) para generar el ZIP.
    """
    # Datos del evento
    event_result = await db.execute(text("""
        SELECT name, location, start_date
        FROM events
        WHERE id = CAST(:eid AS UUID)
    """), {"eid": event_id})
    event_row = event_result.fetchone()
    if not event_row:
        raise ValueError(f"Evento {event_id} no encontrado")

    event_name = event_row.name or "Evento"
    event_location = event_row.location or ""
    event_date = event_row.start_date.isoformat() if event_row.start_date else None

    # Facturas pagadas con firma
    result = await db.execute(text("""
        SELECT pr.id, pr.invoice_number, pr.payment_amount,
               pr.signature_data, pr.paid_at, pr.role_name_snapshot,
               u.first_name, u.last_name, u.document_number, u.phone
        FROM payroll_records pr
        JOIN operators o ON o.id = pr.operator_id
        JOIN users u ON u.id = o.user_id
        WHERE pr.event_id = CAST(:eid AS UUID)
          AND pr.status = 'paid'
          AND pr.signature_data IS NOT NULL
        ORDER BY u.first_name, u.last_name
    """), {"eid": event_id})

    invoices = []
    for row in result.fetchall():
        full_name = f"{row.first_name} {row.last_name}"
        invoices.append({
            "invoice_number": row.invoice_number,
            "paid_at": row.paid_at.isoformat() if row.paid_at else None,
            "payment_amount": float(row.payment_amount or 0),
            "role_name": row.role_name_snapshot,
            "signature_data": row.signature_data,
            "operator_name": full_name,
            "operator_document": row.document_number or "",
            "operator_phone": row.phone or "",
            "event_name": event_name,
            "event_location": event_location,
            "event_date": event_date,
            "company": "A&C Eventos",
        })

    return invoices, event_name


async def main():
    parser = argparse.ArgumentParser(
        description="Genera un ZIP con todas las facturas PDF de un evento"
    )
    parser.add_argument("--event-id", required=True, help="UUID del evento")
    parser.add_argument(
        "--output",
        default=None,
        help="Ruta del archivo .zip de salida (default: ./Recibos_de_Caja_<Evento>.zip)",
    )
    args = parser.parse_args()

    print("\n" + "=" * 60)
    print("  GENERACIÓN MASIVA DE FACTURAS PDF")
    print("=" * 60)
    print(f"  Evento: {args.event_id}")

    engine = await get_engine()
    S = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    try:
        async with S() as db:
            invoices, event_name = await fetch_invoices(db, args.event_id)
    finally:
        await engine.dispose()

    print(f"  Evento: '{event_name}'")
    print(f"  📊 Facturas pagadas con firma: {len(invoices)}")

    if not invoices:
        print("\n  ⚠️  No hay facturas pagadas con firma para este evento.")
        return

    # Mostrar resumen de montos
    total = sum(inv["payment_amount"] for inv in invoices)
    print(f"  💰 Total a pagar: ${total:,.0f} COP")

    zero_count = sum(1 for inv in invoices if inv["payment_amount"] == 0)
    if zero_count > 0:
        print(f"  ⚠️  {zero_count} factura(s) con monto en 0 — ejecuta "
              f"fix_invoice_amounts.py primero")

    # Generar ZIP
    print("\n  🔄 Generando PDFs...")
    zip_bytes = generate_invoices_zip(invoices, event_name=event_name)

    # Determinar ruta de salida
    if args.output:
        out_path = args.output
    else:
        # Sanitizar nombre de evento para el archivo
        import unicodedata, re
        def _sanitize(t):
            t = unicodedata.normalize("NFKD", t)
            t = t.encode("ascii", "ignore").decode("ascii")
            t = re.sub(r"[^A-Za-z0-9_\-]", "_", t.strip().replace(" ", "_"))
            return re.sub(r"_+", "_", t).strip("_") or "Evento"
        out_path = f"Recibos_de_Caja_{_sanitize(event_name)}.zip"

    with open(out_path, "wb") as f:
        f.write(zip_bytes)

    print(f"\n  ✅ ZIP generado: {out_path}")
    print(f"     📦 Tamaño: {len(zip_bytes) / 1024:.1f} KB")
    print(f"     📄 Facturas: {len(invoices)}")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    asyncio.run(main())