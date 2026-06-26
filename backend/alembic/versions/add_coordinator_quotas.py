"""add coordinator quotas + admitted_by

Revision ID: add_coordinator_quotas
Revises: add_event_only_roles
Create Date: 2026-06-26

Añade:
1. Tabla 'event_coordinator_quotas' para cupos máximos por coordinador/evento.
2. Columna 'admitted_by' a 'event_assignments' (coordinador que admite).
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
import uuid


# revision identifiers, used by Alembic.
revision = 'add_coordinator_quotas'
down_revision = 'add_event_only_roles'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1) Tabla de cupos por coordinador
    op.create_table(
        'event_coordinator_quotas',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('event_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('events.id', ondelete='CASCADE'), nullable=False),
        sa.Column('coordinator', sa.String(100), nullable=False,
                  comment="Nombre del coordinador en MAYÚSCULAS (match programmed_by)"),
        sa.Column('quota', sa.Integer(), nullable=False, comment="Cupo máximo"),
    )
    op.create_index('ix_event_coordinator_quotas_event_id', 'event_coordinator_quotas', ['event_id'])
    op.create_index(
        'uq_event_coordinator',
        'event_coordinator_quotas', ['event_id', 'coordinator'],
        unique=True,
    )

    # 2) Columna admitted_by en event_assignments
    op.add_column('event_assignments',
        sa.Column('admitted_by', sa.String(100), nullable=True,
                  comment="Coordinador que admitió al operador (cupo). Default = programmed_by"))

    # 3) Backfill: admitted_by = programmed_by donde admitted_by sea NULL
    op.execute(
        "UPDATE event_assignments SET admitted_by = programmed_by "
        "WHERE admitted_by IS NULL AND programmed_by IS NOT NULL"
    )


def downgrade() -> None:
    op.drop_column('event_assignments', 'admitted_by')
    op.drop_index('uq_event_coordinator', table_name='event_coordinator_quotas')
    op.drop_index('ix_event_coordinator_quotas_event_id', table_name='event_coordinator_quotas')
    op.drop_table('event_coordinator_quotas')