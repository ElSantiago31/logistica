"""add uniform fields to event_assignments

Revision ID: add_uniform_fields
Revises: remove_shoe_pants_size
Create Date: 2026-06-13 18:03:00.000000

Agrega shirt_number, jacket_number y cap_number a event_assignments
para el control de indumentaria entregada en el check-in.
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'add_uniform_fields'
down_revision = 'remove_shoe_pants_size'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('event_assignments', sa.Column('shirt_number', sa.String(length=20), nullable=True, comment='Número de camisa asignada'))
    op.add_column('event_assignments', sa.Column('jacket_number', sa.String(length=20), nullable=True, comment='Número de chaqueta asignada'))
    op.add_column('event_assignments', sa.Column('cap_number', sa.String(length=20), nullable=True, comment='Número de gorra asignada'))


def downgrade() -> None:
    op.drop_column('event_assignments', 'cap_number')
    op.drop_column('event_assignments', 'jacket_number')
    op.drop_column('event_assignments', 'shirt_number')