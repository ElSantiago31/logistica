"""add rut_deadline_at to operators

Revision ID: add_rut_deadline
Revises: add_operator_event_only
Create Date: 2026-10-01

Agrega la columna `operators.rut_deadline_at` (DateTime NULL): plazo UTC
para subir el RUT cuando el registro se hizo sin él (RUT ahora opcional).
NULL = RUT ya cargado o plazo no aplica.

Backfill: los operadores EXISTENTES sin RUT (no "solo evento") reciben un
plazo de gracia de 15 días desde la ejecución de la migración.
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'add_rut_deadline'
down_revision = 'add_operator_event_only'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        'operators',
        sa.Column(
            'rut_deadline_at',
            sa.DateTime(timezone=True),
            nullable=True,
            comment='Plazo (UTC) para subir el RUT tras registro sin él; NULL = RUT cargado o no aplica',
        ),
    )
    # Backfill: 15 días de gracia para operadores existentes sin RUT.
    op.execute(
        "UPDATE operators SET rut_deadline_at = now() + INTERVAL '15 days' "
        "WHERE (rut_path IS NULL OR rut_path = '') "
        "AND (event_only IS NULL OR event_only = false)"
    )


def downgrade() -> None:
    op.drop_column('operators', 'rut_deadline_at')