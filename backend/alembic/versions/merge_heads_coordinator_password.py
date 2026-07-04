"""merge heads: add_coordinator_op_fk + add_password_reset_tokens

Revision ID: merge_coord_pwd
Revises: add_coordinator_op_fk, add_password_reset_tokens
Create Date: 2026-07-04

Merge migration: unifica las dos cabezas (heads) de Alembic que surgieron al
crear 'add_coordinator_op_fk' y 'add_password_reset_tokens' en paralelo,
ambas partiendo de la base 'add_uniform_returned_at'.

Sin esta migración, 'alembic upgrade head' falla con error de multiple heads.

No realiza cambios en el esquema (es un nodo de merge vacío).
"""
from alembic import op


# revision identifiers, used by Alembic.
revision = 'merge_coord_pwd'
down_revision = ('add_coordinator_op_fk', 'add_password_reset_tokens')
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Merge node: no-op. Solo une las dos ramas.
    pass


def downgrade() -> None:
    # Merge node: no-op.
    pass