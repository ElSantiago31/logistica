"""add uniform_returned_at to event_assignments

Revision ID: add_uniform_returned_at
Revises: add_coordinator_quotas
Create Date: 2026-06-27

Añade campo uniform_returned_at a la tabla 'event_assignments'
para registrar la fecha/hora de devolución de uniforme por intendencia.
NULL = pendiente de devolución.

FIX: El down_revision original apuntaba a 'add_uniform_fields' lo que creaba
un conflicto de múltiples heads en Alembic (add_coordinator_quotas y
add_uniform_returned_at eran ambos heads). Se corrige para que apunte al
head real de la cadena principal (add_coordinator_quotas).
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'add_uniform_returned_at'
down_revision = 'add_coordinator_quotas'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('event_assignments',
        sa.Column('uniform_returned_at', sa.DateTime(timezone=True), nullable=True,
                  comment="Fecha/hora de devolución de uniforme. NULL = pendiente."))


def downgrade() -> None:
    op.drop_column('event_assignments', 'uniform_returned_at')