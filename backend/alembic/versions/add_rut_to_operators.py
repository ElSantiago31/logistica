"""add rut_path to operators

Revision ID: add_rut_to_operators
Revises: merge_coord_pwd
Create Date: 2026-07-09

Agrega la columna 'rut_path' a la tabla operators para almacenar la ruta
del archivo PDF del RUT (Registro Único Tributario) del operador.

El RUT es obligatorio en el registro público y queda pendiente de aprobación
por parte del superadmin.
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'add_rut_to_operators'
down_revision = 'merge_coord_pwd'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('operators', sa.Column(
        'rut_path', sa.String(length=500), nullable=True,
        comment='Ruta del PDF del RUT comprimido (/static/rut/...)',
    ))


def downgrade() -> None:
    op.drop_column('operators', 'rut_path')