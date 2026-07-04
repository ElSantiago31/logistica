"""add coordinator operator FK + programmed_by_operator_id

Revision ID: add_coordinator_op_fk
Revises: replace_arl_with_pension_fund
Create Date: 2026-07-03

Añade soporte al nuevo flujo de coordinadores+cupos para eventos nuevos:
1. event_coordinator_quotas.coordinator_operator_id (FK a operators.id, nullable).
   - Recrea el índice único 'uq_event_coordinator' como parcial (solo cuando
     coordinator_operator_id IS NULL, para datos legacy).
   - Crea índice único parcial 'uq_event_coordinator_operator' (nuevo flujo).
2. event_assignments.programmed_by_operator_id (FK a operators.id, nullable).
3. event_assignments.admitted_by_operator_id (FK a operators.id, nullable).

No hace backfill: los datos legacy (Futbolfest) conservan su flujo por nombre.
Solo los eventos nuevos usan las FKs.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = 'add_coordinator_op_fk'
down_revision = 'replace_arl_with_pension_fund'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1) event_coordinator_quotas: añadir FK al operador-coordinador.
    op.add_column(
        'event_coordinator_quotas',
        sa.Column(
            'coordinator_operator_id',
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey('operators.id', ondelete='SET NULL'),
            nullable=True,
            comment="Operador-coordinador (nuevo flujo). NULL en datos legacy.",
        ),
    )
    op.create_index(
        'ix_event_coordinator_quotas_coordinator_operator_id',
        'event_coordinator_quotas',
        ['coordinator_operator_id'],
    )

    # Recrear el índice único como PARCIAL (legacy: solo cuando FK es NULL).
    # Antes era único simple sobre (event_id, coordinator); ahora debe permitir
    # múltiples filas con coordinator_operator_id NOT NULL controladas por el
    # otro índice, y seguir siendo único para las legacy.
    op.drop_index('uq_event_coordinator', table_name='event_coordinator_quotas')
    op.create_index(
        'uq_event_coordinator',
        'event_coordinator_quotas',
        ['event_id', 'coordinator'],
        unique=True,
        postgresql_where=sa.text('coordinator_operator_id IS NULL'),
        sqlite_where=sa.text('coordinator_operator_id IS NULL'),
    )
    op.create_index(
        'uq_event_coordinator_operator',
        'event_coordinator_quotas',
        ['event_id', 'coordinator_operator_id'],
        unique=True,
        postgresql_where=sa.text('coordinator_operator_id IS NOT NULL'),
        sqlite_where=sa.text('coordinator_operator_id IS NOT NULL'),
    )

    # 2) event_assignments: FKs al operador-coordinador.
    op.add_column(
        'event_assignments',
        sa.Column(
            'programmed_by_operator_id',
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey('operators.id', ondelete='SET NULL'),
            nullable=True,
            comment="Operador-coordinador que programó a este operador en el evento",
        ),
    )
    op.add_column(
        'event_assignments',
        sa.Column(
            'admitted_by_operator_id',
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey('operators.id', ondelete='SET NULL'),
            nullable=True,
            comment="Operador-coordinador que admitió a este operador (cupo)",
        ),
    )
    op.create_index(
        'ix_event_assignments_programmed_by_operator_id',
        'event_assignments',
        ['programmed_by_operator_id'],
    )
    op.create_index(
        'ix_event_assignments_admitted_by_operator_id',
        'event_assignments',
        ['admitted_by_operator_id'],
    )


def downgrade() -> None:
    op.drop_index(
        'ix_event_assignments_admitted_by_operator_id',
        table_name='event_assignments',
    )
    op.drop_index(
        'ix_event_assignments_programmed_by_operator_id',
        table_name='event_assignments',
    )
    op.drop_column('event_assignments', 'admitted_by_operator_id')
    op.drop_column('event_assignments', 'programmed_by_operator_id')

    op.drop_index('uq_event_coordinator_operator', table_name='event_coordinator_quotas')
    op.drop_index('uq_event_coordinator', table_name='event_coordinator_quotas')
    op.create_index(
        'uq_event_coordinator',
        'event_coordinator_quotas',
        ['event_id', 'coordinator'],
        unique=True,
    )
    op.drop_index(
        'ix_event_coordinator_quotas_coordinator_operator_id',
        table_name='event_coordinator_quotas',
    )
    op.drop_column('event_coordinator_quotas', 'coordinator_operator_id')