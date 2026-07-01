"""replace ARL with pension_fund

Revision ID: replace_arl_with_pension_fund
Revises: add_uniform_returned_at
Create Date: 2026-07-01

Elimina el catálogo de ARL y lo reemplaza por "Fondo de Pensión".
- Renombra la tabla 'arl' -> 'pension_fund'
- Renombra la FK 'operators.arl_id' -> 'operators.pension_fund_id'
- Reemplaza los registros del catálogo por los 6 fondos de pensión
- Los operadores que tenían arl_id conservan el enlace (los UUIDs se mantienen,
  pero los nombres del catálogo cambian; se recomienda re-asignar manualmente).

Reversible: el downgrade revierte el renombrado y restaura los ARLs originales.
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'replace_arl_with_pension_fund'
down_revision = 'add_uniform_returned_at'
branch_labels = None
depends_on = None


# Catálogo de Fondos de Pensión (reemplaza ARLs)
PENSION_FUNDS = [
    ("Colpensiones", "COLPENSIONES"),
    ("Porvenir", "PORVENIR"),
    ("Protección", "PROTECCION"),
    ("Colfondos", "COLFONDOS"),
    ("Skandia Pensiones y Cesantías", "SKANDIA"),
    ("No Suministra", "NO-SUMINISTRA"),
]

# Catálogo de ARLs original (para downgrade)
ARLS_BACKUP = [
    ("ARL SURA", "ARL-SURA"),
    ("Positiva Compañía de Seguros", "POSITIVA"),
    ("ARL Colmena", "ARL-COLMENA"),
    ("AXA Colpatria", "AXA-COLPATRIA"),
]


def upgrade() -> None:
    # 1. Renombrar tabla arl -> pension_fund
    op.rename_table('arl', 'pension_fund')

    # 2. Renombrar la FK en operators: arl_id -> pension_fund_id
    # En Postgres, alterar el nombre de la columna (la FK se mantiene,
    # solo cambia el nombre de la columna).
    op.alter_column(
        'operators', 'arl_id',
        new_column_name='pension_fund_id',
        existing_type=sa.dialects.postgresql.UUID(),
        existing_nullable=True,
    )

    # 3. Limpiar el catálogo viejo de ARLs y sembrar los fondos de pensión.
    op.execute("UPDATE pension_fund SET is_active = false")
    for name, code in PENSION_FUNDS:
        op.execute(
            sa.text(
                "INSERT INTO pension_fund (id, name, code, is_active) "
                "VALUES (gen_random_uuid(), :name, :code, true) "
                "ON CONFLICT (name) DO UPDATE SET code = :code, is_active = true"
            ).bindparams(name=name, code=code)
        )


def downgrade() -> None:
    # 1. Restaurar catálogo de ARLs (limpiar pension_fund y reinsertar ARLs)
    op.execute("UPDATE pension_fund SET is_active = false")
    for name, code in ARLS_BACKUP:
        op.execute(
            sa.text(
                "INSERT INTO pension_fund (id, name, code, is_active) "
                "VALUES (gen_random_uuid(), :name, :code, true) "
                "ON CONFLICT (name) DO UPDATE SET code = :code, is_active = true"
            ).bindparams(name=name, code=code)
        )

    # 2. Renombrar FK de vuelta: pension_fund_id -> arl_id
    op.alter_column(
        'operators', 'pension_fund_id',
        new_column_name='arl_id',
        existing_type=sa.dialects.postgresql.UUID(),
        existing_nullable=True,
    )

    # 3. Renombrar tabla pension_fund -> arl
    op.rename_table('pension_fund', 'arl')