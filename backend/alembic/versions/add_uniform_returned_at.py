"""add uniform_returned_at to event_assignments

Revision ID: add_uniform_returned_at
Revises: add_uniform_fields
Create Date: 2026-06-27

Añade campo uniform_returned_at a la tabla 'event_assignments'
para registrar la fecha/hora de devolución de uniforme por intendencia.
NULL = pendiente de devolución.
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'add_uniform_returned_at'
down_revision = 'add_uniform_fields'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('event_assignments',
        sa.Column('uniform_returned_at', sa.DateTime(timezone=True), nullable=True,
                  comment="Fecha/hora de devolución de uniforme. NULL = pendiente."))


def downgrade() -> None:
    op.drop_column('event_assignments', 'uniform_returned_at')