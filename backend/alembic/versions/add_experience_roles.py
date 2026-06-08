"""add experience_roles to operators

Revision ID: add_exp_roles
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers
revision = 'add_exp_roles'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('operators', sa.Column('experience_roles', sa.Text(), nullable=True, comment='JSON list of role IDs with experience'))


def downgrade() -> None:
    op.drop_column('operators', 'experience_roles')