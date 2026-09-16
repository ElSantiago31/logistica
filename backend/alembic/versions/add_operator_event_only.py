"""add operators.event_only (Incorporación Rápida)

Revision ID: add_operator_event_only
Revises: add_stage_to_events
Create Date: 2026-09-16

Agrega la columna `operators.event_only` (bool, NOT NULL, default false)
para marcar operadores "solo evento" creados por el botón ⚡ Incorporación
Rápida del detalle de evento: usuario fantasma inactivo (is_active=False,
email=NULL, password aleatoria desconocida) que solo vive mientras exista
una asignación de un evento activo. Ver app/services/quick_add.py.
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'add_operator_event_only'
down_revision = 'add_stage_to_events'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        'operators',
        sa.Column(
            'event_only',
            sa.Boolean(),
            nullable=False,
            server_default=sa.text('false'),
            comment="True: operador 'solo evento' (Incorporación Rápida). Usuario fantasma inactivo.",
        ),
    )


def downgrade() -> None:
    op.drop_column('operators', 'event_only')