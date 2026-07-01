#!/usr/bin/env python
"""Fix de payment_amount para facturas de un evento.

PROBLEMA:
    Algunos PayrollRecord tienen payment_amount = 0 (el monto nunca se seteó
    porque el operador firmó antes de que la tarifa estuviera configurada, o
    el rate_applied venía NULL).

SOLUCIÓN:
    Este script actualiza payment_amount al valor indicado (default 100000)
    para todos los registros de un evento que estén en status='paid' con
    signature_data y payment_amount = 0.

USO:
    python -m scripts.fix_invoice_amounts --event-id <UUID>            # fix real
    python -m scripts.fix_invoice_amounts --event-id <UUID> --dry-run  # simular
    python -m scripts.fix_invoice_amounts --event-id <UUID> --amount 120000
"""
import argparse
import asyncio
import sys
import os

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


async def fix_amounts(db: AsyncSession, event_id: str, amount: float, dry_run: bool = False):
    """Actualiza payment_amount=0 -> amount para facturas pagadas con firma."""
    print("\n" + "=" * 60)
    print("  FIX DE MONTOS DE FACTURAS")
    print("=" * 60)
    print(f"  Evento:  {event_id}")
    print(f"  Monto:   ${amount:,.0f} COP")
    if dry_run:
        print(f"  ⚠️  DRY RUN — no se guardará nada")
    print()

    # Contar registros que necesitan fix
    count_result = await db.execute(text("""
        SELECT COUNT(*) as total
        FROM payroll_records
        WHERE event_id = CAST(:eid AS UUID)
          AND status = 'paid'
          AND signature_data IS NOT NULL
          AND payment_amount = 0
    """), {"eid": event_id})
    total_to_fix = count_result.scalar() or 0

    # Contar registros totales pagados con firma (para contexto)
    total_paid_result = await db.execute(text("""
        SELECT COUNT(*) as total
        FROM payroll_records
        WHERE event_id = CAST(:eid AS UUID)
          AND status = 'paid'
          AND signature_data IS NOT NULL
    """), {"eid": event_id})
    total_paid = total_paid_result.scalar() or 0

    print(f"  📊 Facturas pagadas con firma: {total_paid}")
    print(f"  🔧 Con monto en 0 (a corregir): {total_to_fix}")
    print()

    if total_to_fix == 0:
        print("  ✅ No hay facturas con monto en 0. Nada que corregir.")
        return

    # Mostrar detalle de los que se van a actualizar
    detail_result = await db.execute(text("""
        SELECT pr.id, pr.invoice_number, pr.payment_amount,
               u.first_name, u.last_name, u.document_number
        FROM payroll_records pr
        JOIN operators o ON o.id = pr.operator_id
        JOIN users u ON u.id = o.user_id
        WHERE pr.event_id = CAST(:eid AS UUID)
          AND pr.status = 'paid'
          AND pr.signature_data IS NOT NULL
          AND pr.payment_amount = 0
        ORDER BY u.first_name, u.last_name
    """), {"eid": event_id})

    rows = detail_result.fetchall()
    for i, row in enumerate(rows, 1):
        full_name = f"{row.first_name} {row.last_name}"
        print(f"  [{i}] {full_name} ({row.document_number}) — {row.invoice_number or 'sin factura'}")

    if dry_run:
        print(f"\n  ⚠️  DRY RUN: se actualizarían {total_to_fix} registros a ${amount:,.0f}")
        return

    # UPDATE real
    result = await db.execute(text("""
        UPDATE payroll_records
        SET payment_amount = :amount
        WHERE event_id = CAST(:eid AS UUID)
          AND status = 'paid'
          AND signature_data IS NOT NULL
          AND payment_amount = 0
    """), {"eid": event_id, "amount": amount})

    updated = result.rowcount
    await db.commit()

    print("\n" + "=" * 60)
    print("  RESUMEN")
    print("=" * 60)
    print(f"  ✅ Actualizados: {updated} registros → ${amount:,.0f} COP cada uno")
    print(f"  📊 Total facturas pagadas con firma: {total_paid}")
    print("=" * 60 + "\n")


async def main():
    parser = argparse.ArgumentParser(
        description="Fix de payment_amount para facturas de un evento"
    )
    parser.add_argument(
        "--event-id",
        required=True,
        help="UUID del evento",
    )
    parser.add_argument(
        "--amount",
        type=float,
        default=100000.0,
        help="Monto a aplicar (default: 100000)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Simular sin guardar nada",
    )
    args = parser.parse_args()

    engine = await get_engine()
    S = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with S() as db:
        await fix_amounts(db, args.event_id, args.amount, dry_run=args.dry_run)
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())