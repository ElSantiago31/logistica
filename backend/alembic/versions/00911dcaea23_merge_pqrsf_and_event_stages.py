"""merge_pqrsf_and_event_stages

Revision ID: 00911dcaea23
Revises: add_event_date_to_stages, add_pqrsf_tables
Create Date: 2026-08-11 22:54:17.978036

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '00911dcaea23'
down_revision: Union[str, None] = ('add_event_date_to_stages', 'add_pqrsf_tables')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
