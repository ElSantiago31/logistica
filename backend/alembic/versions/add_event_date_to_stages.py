"""add event_date column to site_stages

Revision ID: add_event_date_to_stages
Revises: add_site_stages
Create Date: 2026-07-28

Agrega la columna ``event_date`` (texto libre, nullable) a ``site_stages``
para permitir mostrar la fecha/periodo del escenario en la home pública
y editarla desde el panel admin de contenido.
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'add_event_date_to_stages'
down_revision = 'add_site_stages'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        'site_stages',
        sa.Column(
            'event_date',
            sa.String(40),
            nullable=True,
            comment="Fecha/periodo del evento (texto libre): ej. '2024', 'Nov 2023'",
        ),
    )


def downgrade() -> None:
    op.drop_column('site_stages', 'event_date')