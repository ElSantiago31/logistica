"""add operator incidents and bans tables

Revision ID: add_incidents_bans
Revises: rm_intendencia_qr
Create Date: 2026-07-10

Añade:
  - Tabla 'operator_incidents' (novedades operativas + vetos por evento)
  - Tabla 'operator_bans' (historial de vetos, con índice único parcial
    para garantizar un solo veto activo por operador)
  - Columna 'is_banned' en 'operators' (snapshot del estado de veto)

Nota: Usa sa.Uuid() (UUID nativo de PostgreSQL) para coincidir con el tipo
de las columnas referenciadas (events.id, operators.id, users.id). Las
versiones previas que usaban sa.String(36) fallaban con DatatypeMismatchError.
La migración es IDEMPOTENTE para no fallar ante estados parciales.
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'add_incidents_bans'
down_revision = 'rm_intendencia_qr'
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    # --- Tabla operator_incidents ---
    if not inspector.has_table('operator_incidents'):
        op.create_table(
            'operator_incidents',
            sa.Column('id', sa.Uuid(), primary_key=True, nullable=False),
            sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column('event_id', sa.Uuid(),
                      sa.ForeignKey('events.id', ondelete='CASCADE'), nullable=False, index=True),
            sa.Column('operator_id', sa.Uuid(),
                      sa.ForeignKey('operators.id', ondelete='CASCADE'), nullable=False, index=True),
            sa.Column('recorded_by', sa.Uuid(),
                      sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
            sa.Column('incident_type', sa.String(50), nullable=False,
                      comment="doble_turno | llegada_tarde | salida_anticipada | incumplimiento | "
                              "llamado_atencion | observacion | otro | veto"),
            sa.Column('description', sa.Text(), nullable=False),
            sa.Column('is_veto', sa.Boolean(), nullable=False, server_default=sa.false(),
                      comment="True si la novedad corresponde a un veto"),
        )

    # --- Tabla operator_bans ---
    if not inspector.has_table('operator_bans'):
        op.create_table(
            'operator_bans',
            sa.Column('id', sa.Uuid(), primary_key=True, nullable=False),
            sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column('operator_id', sa.Uuid(),
                      sa.ForeignKey('operators.id', ondelete='CASCADE'), nullable=False, index=True),
            sa.Column('banned_by', sa.Uuid(),
                      sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
            sa.Column('reason', sa.Text(), nullable=False),
            sa.Column('observations', sa.Text(), nullable=True),
            sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.true(), index=True),
            sa.Column('unbanned_by', sa.Uuid(),
                      sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
            sa.Column('unbanned_at', sa.DateTime(timezone=True), nullable=True),
            sa.Column('unban_reason', sa.Text(), nullable=True),
        )

        # Índice único parcial: solo un veto activo por operador.
        op.create_index(
            'uq_operator_ban_active',
            'operator_bans',
            ['operator_id'],
            unique=True,
            postgresql_where=sa.text('is_active = true'),
            sqlite_where=sa.text('is_active = 1'),
        )

    # --- Columna is_banned en operators ---
    columns = [c['name'] for c in inspector.get_columns('operators')]
    if 'is_banned' not in columns:
        op.add_column(
            'operators',
            sa.Column('is_banned', sa.Boolean(), nullable=False, server_default=sa.false(), index=True,
                      comment="True si el operador está vetado (no puede iniciar sesión)"),
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    columns = [c['name'] for c in inspector.get_columns('operators')]
    if 'is_banned' in columns:
        op.drop_column('operators', 'is_banned')

    existing_indexes = [
        idx.get('name')
        for idx in inspector.get_indexes('operator_bans')
    ] if inspector.has_table('operator_bans') else []
    if 'uq_operator_ban_active' in existing_indexes:
        op.drop_index('uq_operator_ban_active', table_name='operator_bans')

    if inspector.has_table('operator_bans'):
        op.drop_table('operator_bans')
    if inspector.has_table('operator_incidents'):
        op.drop_table('operator_incidents')