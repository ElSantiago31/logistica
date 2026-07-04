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

Nota: IDEMPOTENTE. Verifica existencia de columnas/índices antes de operar,
para no fallar si un deploy anterior dejó estado parcial en la DB.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = 'add_coordinator_op_fk'
down_revision = 'replace_arl_with_pension_fund'
branch_labels = None
depends_on = None


def _has_column(bind, table, column):
    inspector = sa.inspect(bind)
    cols = [c['name'] for c in inspector.get_columns(table)]
    return column in cols


def _index_names(bind, table):
    inspector = sa.inspect(bind)
    return [idx.get('name') for idx in inspector.get_indexes(table)]


def upgrade() -> None:
    bind = op.get_bind()

    # 1) event_coordinator_quotas: añadir FK al operador-coordinador.
    if not _has_column(bind, 'event_coordinator_quotas', 'coordinator_operator_id'):
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

    idxs = _index_names(bind, 'event_coordinator_quotas')
    if 'ix_event_coordinator_quotas_coordinator_operator_id' not in idxs:
        op.create_index(
            'ix_event_coordinator_quotas_coordinator_operator_id',
            'event_coordinator_quotas',
            ['coordinator_operator_id'],
        )

    # Recrear el índice único como PARCIAL (legacy: solo cuando FK es NULL).
    if 'uq_event_coordinator' in idxs:
        op.drop_index('uq_event_coordinator', table_name='event_coordinator_quotas')
    op.create_index(
        'uq_event_coordinator',
        'event_coordinator_quotas',
        ['event_id', 'coordinator'],
        unique=True,
        postgresql_where=sa.text('coordinator_operator_id IS NULL'),
        sqlite_where=sa.text('coordinator_operator_id IS NULL'),
    )
    if 'uq_event_coordinator_operator' not in idxs:
        op.create_index(
            'uq_event_coordinator_operator',
            'event_coordinator_quotas',
            ['event_id', 'coordinator_operator_id'],
            unique=True,
            postgresql_where=sa.text('coordinator_operator_id IS NOT NULL'),
            sqlite_where=sa.text('coordinator_operator_id IS NOT NULL'),
        )

    # 2) event_assignments: FKs al operador-coordinador.
    if not _has_column(bind, 'event_assignments', 'programmed_by_operator_id'):
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
    if not _has_column(bind, 'event_assignments', 'admitted_by_operator_id'):
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

    a_idxs = _index_names(bind, 'event_assignments')
    if 'ix_event_assignments_programmed_by_operator_id' not in a_idxs:
        op.create_index(
            'ix_event_assignments_programmed_by_operator_id',
            'event_assignments',
            ['programmed_by_operator_id'],
        )
    if 'ix_event_assignments_admitted_by_operator_id' not in a_idxs:
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