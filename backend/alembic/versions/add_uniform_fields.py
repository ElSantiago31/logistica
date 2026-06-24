"""add uniform fields to event_assignments

Revision ID: add_uniform_fields
Revises: add_event_staff_assignments
Create Date: 2026-06-23

Añade campos shirt_number, jacket_number, cap_number a la tabla
'event_assignments' para gestión de indumentaria por intendencia.
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'add_uniform_fields'
down_revision = 'add_event_staff_assignments'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('event_assignments',
        sa.Column('shirt_number', sa.String(20), nullable=True, comment="Número de camisa asignada"))
    op.add_column('event_assignments',
        sa.Column('jacket_number', sa.String(20), nullable=True, comment="Número de chaqueta asignada"))
    op.add_column('event_assignments',
        sa.Column('cap_number', sa.String(20), nullable=True, comment="Número de gorra asignada"))


def downgrade() -> None:
    op.drop_column('event_assignments', 'cap_number')
    op.drop_column('event_assignments', 'jacket_number')
    op.drop_column('event_assignments', 'shirt_number')