"""add education_level to operators

Revision ID: add_education_level
Revises: add_exp_roles
Create Date: 2026-06-08 12:39:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'add_education_level'
down_revision = 'add_exp_roles'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('operators', sa.Column('education_level', sa.String(length=50), nullable=True, comment='Nivel de estudio: primaria,secundaria,tecnico,tecnologo,universitario,postgrado'))


def downgrade() -> None:
    op.drop_column('operators', 'education_level')