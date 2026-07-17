"""fix operator_incidents.is_active column

Revision ID: fix_incidents_is_active
Revises: add_incidents_bans
Create Date: 2026-07-12

Corrige la tabla 'operator_incidents' añadiendo la columna 'is_active' que
el modelo ORM (BaseModel) espera pero la migración add_incidents_bans omitió.

Esto causaba:
    asyncpg.exceptions.UndefinedColumnError:
        column operator_incidents.is_active does not exist
y un HTTP 500 en GET /api/incidents.

La migración es IDEMPOTENTE: no falla si la columna ya existe.
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'fix_incidents_is_active'
down_revision = 'add_incidents_bans'
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if inspector.has_table('operator_incidents'):
        columns = [c['name'] for c in inspector.get_columns('operator_incidents')]
        if 'is_active' not in columns:
            op.add_column(
                'operator_incidents',
                sa.Column(
                    'is_active', sa.Boolean(),
                    nullable=False,
                    server_default=sa.true(),
                ),
            )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if inspector.has_table('operator_incidents'):
        columns = [c['name'] for c in inspector.get_columns('operator_incidents')]
        if 'is_active' in columns:
            op.drop_column('operator_incidents', 'is_active')