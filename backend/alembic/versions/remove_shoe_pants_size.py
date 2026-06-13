"""remove shoe_size and pants_size from operators

Revision ID: remove_shoe_pants_size
Revises: 4324281308a3, add_blocked_documents
Create Date: 2026-06-13 15:32:00.000000

Merge de las dos cabezas (4324281308a3 y add_blocked_documents) y elimina
las columnas shoe_size y pants_size de operators, que ya no se usan.
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'remove_shoe_pants_size'
down_revision = ('4324281308a3', 'add_blocked_documents')
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_column('operators', 'shoe_size')
    op.drop_column('operators', 'pants_size')


def downgrade() -> None:
    op.add_column('operators', sa.Column('pants_size', sa.String(length=10), nullable=True))
    op.add_column('operators', sa.Column('shoe_size', sa.String(length=10), nullable=True))