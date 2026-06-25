"""add programmed_by to event_assignments

Revision ID: add_programmed_by
Revises: add_uniform_fields
Create Date: 2026-06-24

Añade el campo 'programmed_by' a la tabla 'event_assignments' para
almacenar el nombre del coordinador que programó/reclutó al operador,
extraído de los formularios de registro (JSON/TXT de inyección).
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'add_programmed_by'
# Merge de las dos ramas: add_uniform_fields y add_event_staff_assignments
down_revision = ('add_uniform_fields', 'add_event_staff_assignments')
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('event_assignments',
        sa.Column('programmed_by', sa.String(100), nullable=True,
                  comment="Coordinador que programó al operador (del formulario de registro)"))


def downgrade() -> None:
    op.drop_column('event_assignments', 'programmed_by')