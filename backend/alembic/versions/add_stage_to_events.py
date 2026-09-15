"""add stage column to event needs/assignments/quotas

Revision ID: add_stage_to_events
Revises: user_email_optional
Create Date: 2026-09-14

Agrega la columna ``stage`` (etapa del evento: previa | avanzada | evento |
desmontaje) a ``event_staff_needs``, ``event_assignments`` y
``event_coordinator_quotas``.

Compatibilidad: NOT NULL con server_default 'evento' → todo dato existente
queda en la etapa "evento" sin backfill manual.

Antes de crear los índices únicos se hace un dedup defensivo:
- event_staff_needs: duplicados (event_id, role_id) → se SUMA quantity_needed
  en la fila más antigua y se borran las demás.
- event_coordinator_quotas: duplicados por flujo (legacy por nombre / nuevo
  por operator_id) → se SUMA quota en la fila más antigua y se borran las demás.
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'add_stage_to_events'
down_revision = 'user_email_optional'
branch_labels = None
depends_on = None

STAGES_TABLES = ("event_staff_needs", "event_assignments", "event_coordinator_quotas")


def upgrade() -> None:
    # 1) Columna stage en las 3 tablas (server_default 'evento').
    for table in STAGES_TABLES:
        op.add_column(
            table,
            sa.Column(
                'stage',
                sa.String(length=20),
                nullable=False,
                server_default='evento',
                comment='Etapa: previa | avanzada | evento | desmontaje',
            ),
        )

    # 2) Dedup defensivo ANTES de índices únicos.
    #    (Solo relevante si existieran duplicados; en BD normal no hace nada.)

    # 2a) event_staff_needs: sumar duplicados en la fila más antigua y borrar el resto.
    #     Primero SUMA (sobre todas las filas), luego DELETE — si se borra antes
    #     la suma se calcularía solo sobre las filas sobrevivientes.
    op.execute("""
        UPDATE event_staff_needs sn
        SET quantity_needed = d.total
        FROM (
            SELECT id,
                   SUM(quantity_needed) OVER (PARTITION BY event_id, role_id) AS total,
                   ROW_NUMBER() OVER (PARTITION BY event_id, role_id ORDER BY created_at, id) AS rn
            FROM event_staff_needs
        ) d
        WHERE sn.id = d.id AND d.rn = 1
    """)
    op.execute("""
        DELETE FROM event_staff_needs
        WHERE id IN (
            SELECT id FROM (
                SELECT id,
                       ROW_NUMBER() OVER (PARTITION BY event_id, role_id ORDER BY created_at, id) AS rn
                FROM event_staff_needs
            ) t WHERE t.rn > 1
        )
    """)

    # 2b) event_coordinator_quotas legacy: conservar la más antigua por (event_id, coordinator).
    op.execute("""
        DELETE FROM event_coordinator_quotas
        WHERE id IN (
            SELECT id FROM (
                SELECT id,
                       ROW_NUMBER() OVER (
                           PARTITION BY event_id, coordinator
                           ORDER BY created_at, id
                       ) AS rn
                FROM event_coordinator_quotas
                WHERE coordinator_operator_id IS NULL
            ) t WHERE t.rn > 1
        )
    """)
    # 2c) event_coordinator_quotas nuevo flujo: conservar la más antigua por
    #     (event_id, coordinator_operator_id).
    op.execute("""
        DELETE FROM event_coordinator_quotas
        WHERE id IN (
            SELECT id FROM (
                SELECT id,
                       ROW_NUMBER() OVER (
                           PARTITION BY event_id, coordinator_operator_id
                           ORDER BY created_at, id
                       ) AS rn
                FROM event_coordinator_quotas
                WHERE coordinator_operator_id IS NOT NULL
            ) t WHERE t.rn > 1
        )
    """)

    # 3) Índices únicos de cuotas: reemplazar los de 2 columnas por 3 columnas (con stage).
    op.drop_index('uq_event_coordinator', table_name='event_coordinator_quotas')
    op.drop_index('uq_event_coordinator_operator', table_name='event_coordinator_quotas')
    op.create_index(
        'uq_event_coordinator',
        'event_coordinator_quotas',
        ['event_id', 'coordinator', 'stage'],
        unique=True,
        postgresql_where=sa.text('coordinator_operator_id IS NULL'),
        sqlite_where=sa.text('coordinator_operator_id IS NULL'),
    )
    op.create_index(
        'uq_event_coordinator_operator',
        'event_coordinator_quotas',
        ['event_id', 'coordinator_operator_id', 'stage'],
        unique=True,
        postgresql_where=sa.text('coordinator_operator_id IS NOT NULL'),
        sqlite_where=sa.text('coordinator_operator_id IS NOT NULL'),
    )

    # 4) Índices para filtrar por etapa.
    op.create_index(op.f('ix_event_staff_needs_stage'), 'event_staff_needs', ['stage'], unique=False)
    op.create_index(op.f('ix_event_assignments_stage'), 'event_assignments', ['stage'], unique=False)

    # 5) Índice único de needs por (event_id, role_id, stage).
    #    El dedup del paso 2a garantiza que no haya duplicados en 'evento';
    #    etapas nuevas no existen aún en datos.
    op.create_index(
        'uq_event_staff_need_role_stage',
        'event_staff_needs',
        ['event_id', 'role_id', 'stage'],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index('uq_event_staff_need_role_stage', table_name='event_staff_needs')
    op.drop_index(op.f('ix_event_assignments_stage'), table_name='event_assignments')
    op.drop_index(op.f('ix_event_staff_needs_stage'), table_name='event_staff_needs')

    # Restaurar índices únicos de cuotas sin stage (dedup por si acaso).
    op.drop_index('uq_event_coordinator_operator', table_name='event_coordinator_quotas')
    op.drop_index('uq_event_coordinator', table_name='event_coordinator_quotas')
    op.execute("""
        DELETE FROM event_coordinator_quotas
        WHERE id IN (
            SELECT id FROM (
                SELECT id,
                       ROW_NUMBER() OVER (
                           PARTITION BY event_id, coordinator
                           ORDER BY created_at, id
                       ) AS rn
                FROM event_coordinator_quotas
            ) t WHERE t.rn > 1
        )
    """)
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

    for table in STAGES_TABLES:
        op.drop_column(table, 'stage')