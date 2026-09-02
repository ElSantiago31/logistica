"""Purga de operadores SIN RUT adjunto (VPS / producción).

Borra PERMANENTEMENTE (hard delete) todos los usuarios con
user_type='operator' cuyo perfil NO tiene RUT (`operators.rut_path`
vacío o NULL). Conserva:

- TODOS los administradores y staff (superadmin, admin, web_admin,
  checkin, intendencia, coordinator) — nunca se tocan.
- Operadores que SÍ adjuntaron RUT (`rut_path` no vacío).

Uso (dentro del contenedor backend en la VPS):

    # 1. DRY-RUN (por defecto): solo lista lo que se borraría
    docker exec logistica_backend python -m scripts.purge_operators_without_rut

    # 2. BORRADO REAL (tras revisar el dry-run y tener backup)
    docker exec logistica_backend python -m scripts.purge_operators_without_rut --execute

Antes de ejecutar con --execute, hacer backup:
    bash scripts/backup.sh
"""
import argparse
import asyncio
import sys

from sqlalchemy import select

from app.database import AsyncSessionLocal
from app.models.operators import Operator
from app.models.users import User
from app.services.documents import delete_id_document_photos, delete_rut_pdf
from app.services.operators import delete_operator


async def fetch_candidates(db) -> list:
    """Operadores (user_type='operator') SIN rut_path válido."""
    result = await db.execute(
        select(User, Operator)
        .join(Operator, Operator.user_id == User.id)
        .where(
            User.user_type == "operator",
            (Operator.rut_path.is_(None)) | (Operator.rut_path == ""),
        )
        .order_by(User.created_at.asc())
    )
    return result.all()


async def fetch_keep_counts(db) -> dict:
    """Conteos de lo que se CONSERVA (para el reporte)."""
    staff = await db.execute(
        select(User).where(User.user_type != "operator")
    )
    with_rut = await db.execute(
        select(User, Operator)
        .join(Operator, Operator.user_id == User.id)
        .where(
            User.user_type == "operator",
            Operator.rut_path.is_not(None),
            Operator.rut_path != "",
        )
    )
    total_ops = await db.execute(
        select(User).where(User.user_type == "operator")
    )
    return {
        "staff": len(staff.scalars().all()),
        "ops_con_rut": len(with_rut.all()),
        "ops_total": len(total_ops.scalars().all()),
    }


async def main(execute: bool) -> int:
    async with AsyncSessionLocal() as db:
        candidates = await fetch_candidates(db)
        keeps = await fetch_keep_counts(db)

        print("=" * 78)
        print("PURGA DE OPERADORES SIN RUT — " + ("EJECUTANDO BORRADO REAL" if execute else "DRY-RUN (no se borra nada)"))
        print("=" * 78)
        print(f"Se CONSERVAN: {keeps['staff']} administradores/staff (user_type != operator)")
        print(f"Se CONSERVAN: {keeps['ops_con_rut']} operadores CON RUT adjunto")
        print(f"Se ELIMINARÁN: {len(candidates)} operadores SIN RUT (de {keeps['ops_total']} operadores totales)")
        print("-" * 78)
        if candidates:
            print(f"{'#':>3}  {'NOMBRE':30} {'DOCUMENTO':16} {'ESTADO':8} {'APROB':6} CREADO")
            for i, (u, op) in enumerate(candidates, 1):
                estado = "activo" if u.is_active else "inactivo"
                aprob = "sí" if u.is_approved else "no"
                print(f"{i:>3}  {(u.first_name or '') + ' ' + (u.last_name or ''):30.30} "
                      f"{(u.document_number or '(sin doc)'):16.16} {estado:8} {aprob:6} "
                      f"{str(u.created_at or '')[:10]}")
        else:
            print("No hay operadores sin RUT — nada que hacer.")
            return 0
        print("-" * 78)

        if not execute:
            print("\nDRY-RUN: no se borró nada. Para ejecutar el borrado real:")
            print("  1. Backup:  bash scripts/backup.sh")
            print("  2. Ejecutar con --execute")
            return 0

        # --- Borrado real ---
        ok, fail = 0, 0
        for i, (u, op) in enumerate(candidates, 1):
            label = f"{u.first_name} {u.last_name} ({u.document_number or 'sin doc'})".strip()
            try:
                # Archivos de disco que delete_operator NO limpia (RUT/cédulas).
                # Sin RUT no debería haber PDF, pero las cédulas sí pueden existir.
                delete_rut_pdf(op.rut_path)
                delete_id_document_photos(op.id_document_front_path, op.id_document_back_path)

                # Hard delete en cascada: nómina, evaluaciones, asignaciones,
                # referidos (CASCADE), tokens, auditoría, perfil y usuario.
                deleted = await delete_operator(db, u.id, hard_delete=True)
                if deleted:
                    ok += 1
                    print(f"[{i}/{len(candidates)}] BORRADO  {label}")
                else:
                    fail += 1
                    print(f"[{i}/{len(candidates)}] OMITIDO  {label} (ya no existe)")
            except Exception as e:  # noqa: BLE001 — reportar y continuar con el resto
                fail += 1
                print(f"[{i}/{len(candidates)}] ERROR    {label}: {e}")

        print("=" * 78)
        print(f"RESULTADO: {ok} eliminados, {fail} con error, "
              f"{keeps['ops_con_rut']} operadores con RUT conservados, "
              f"{keeps['staff']} administradores/staff intactos.")
        return 1 if fail else 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Borra operadores sin RUT (hard delete). Dry-run por defecto."
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Ejecuta el borrado real (sin esta bandera solo muestra el dry-run).",
    )
    args = parser.parse_args()
    sys.exit(asyncio.run(main(args.execute)))
