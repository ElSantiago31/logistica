"""add gender column to operators

Revision ID: add_operator_gender
Revises: add_hierarchy_roles
Create Date: 2026-06-19

Agrega la columna 'gender' a la tabla operators para registrar
el género del operador (Femenino, Masculino).
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'add_operator_gender'
down_revision = 'add_hierarchy_roles'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('operators', sa.Column(
        'gender', sa.String(length=20), nullable=True,
        comment='Género del operador: Femenino, Masculino',
    ))


def downgrade() -> None:
    op.drop_column('operators', 'gender')