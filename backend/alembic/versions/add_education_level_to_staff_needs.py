"""add education_level to event_staff_needs

Revision ID: add_edu_staff
Revises: add_event_audit_log
Create Date: 2026-06-11
"""
from alembic import op
import sqlalchemy as sa

revision = 'add_edu_staff'
down_revision = 'add_event_audit_log'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('event_staff_needs', sa.Column('education_level', sa.String(50), nullable=True,
        comment='Nivel educativo minimo requerido: primaria,secundaria,tecnico,tecnologo,universitario,postgrado'))


def downgrade() -> None:
    op.drop_column('event_staff_needs', 'education_level')