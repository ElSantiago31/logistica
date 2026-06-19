"""add hierarchy_level and area to roles

Revision ID: add_hierarchy_roles
Revises: add_uniform_fields
Create Date: 2026-06-17
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'add_hierarchy_roles'
down_revision = 'add_uniform_fields'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Agregar columnas
    op.add_column('roles', sa.Column(
        'hierarchy_level', sa.Integer(), nullable=False, server_default='3',
        comment='1=Coordinador General, 2=Coordinador de área, 3=Operador',
    ))
    op.add_column('roles', sa.Column(
        'area', sa.String(length=50), nullable=True,
        comment='Área: Emergencias, Logística, Seguridad, etc.',
    ))
    op.create_index('ix_roles_hierarchy_level', 'roles', ['hierarchy_level'])
    op.create_index('ix_roles_area', 'roles', ['area'])

    # Asignar jerarquía a roles existentes según el slug
    # Nivel 1: Coordinador General
    op.execute("UPDATE roles SET hierarchy_level = 1 WHERE slug = 'coordinador_general'")
    # Nivel 2: Coordinadores de área
    op.execute("UPDATE roles SET hierarchy_level = 2, area = 'Grupos' WHERE slug = 'coordinador_grupos'")
    op.execute("UPDATE roles SET hierarchy_level = 2, area = 'Emergencias' WHERE slug = 'coordinador_emergencias'")
    op.execute("UPDATE roles SET hierarchy_level = 2, area = 'Seguridad' WHERE slug = 'lider_seguridad'")
    # Nivel 3: Operadores (resto) — ya tienen server_default=3


def downgrade() -> None:
    op.drop_index('ix_roles_area', table_name='roles')
    op.drop_index('ix_roles_hierarchy_level', table_name='roles')
    op.drop_column('roles', 'area')
    op.drop_column('roles', 'hierarchy_level')