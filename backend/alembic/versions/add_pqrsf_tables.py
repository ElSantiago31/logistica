"""add pqrsf tables (PQRSF submissions + responses)

Revision ID: add_pqrsf_tables
Revises: add_event_audit_log
Create Date: 2026-08-11

Crea las tablas `site_pqrsf` y `site_pqrsf_responses` que respaldan el
sistema de PQRSF (Peticiones, Quejas, Reclamos, Sugerencias y
Felicitaciones) en el sitio público y su gestión desde el panel admin.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = 'add_pqrsf_tables'
down_revision = 'add_event_audit_log'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # --- site_pqrsf ---
    op.create_table(
        'site_pqrsf',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column('created_at', sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False,
                  server_default=sa.text('true')),
        sa.Column('tracking_code', sa.String(20), nullable=False,
                  comment="Código público (ej. PQR-2026-00042)"),
        sa.Column('request_type', sa.String(20), nullable=False,
                  comment="petition|complaint|claim|suggestion|congratulation"),
        sa.Column('subject', sa.String(200), nullable=False),
        sa.Column('full_name', sa.String(160), nullable=False),
        sa.Column('email', sa.String(160), nullable=False),
        sa.Column('phone', sa.String(40), nullable=True),
        sa.Column('company', sa.String(160), nullable=True),
        sa.Column('message', sa.Text(), nullable=False),
        sa.Column('status', sa.String(20), nullable=False,
                  server_default='new',
                  comment="new|in_progress|resolved|closed"),
        sa.Column('priority', sa.String(10), nullable=False,
                  server_default='low',
                  comment="low|medium|high"),
        sa.Column('assigned_to', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('users.id', ondelete='SET NULL'),
                  nullable=True),
        sa.Column('resolved_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('contacted_at', sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index('ix_site_pqrsf_tracking_code', 'site_pqrsf',
                    ['tracking_code'], unique=True)
    op.create_index('ix_site_pqrsf_request_type', 'site_pqrsf', ['request_type'])
    op.create_index('ix_site_pqrsf_email', 'site_pqrsf', ['email'])
    op.create_index('ix_site_pqrsf_status', 'site_pqrsf', ['status'])

    # --- site_pqrsf_responses ---
    op.create_table(
        'site_pqrsf_responses',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column('created_at', sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False,
                  server_default=sa.text('true')),
        sa.Column('pqrsf_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('site_pqrsf.id', ondelete='CASCADE'),
                  nullable=False),
        sa.Column('responded_by', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('users.id', ondelete='SET NULL'),
                  nullable=False),
        sa.Column('subject', sa.String(200), nullable=False),
        sa.Column('body', sa.Text(), nullable=False),
        sa.Column('sent', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('error_message', sa.Text(), nullable=True),
    )
    op.create_index('ix_site_pqrsf_responses_pqrsf_id',
                    'site_pqrsf_responses', ['pqrsf_id'])


def downgrade() -> None:
    op.drop_index('ix_site_pqrsf_responses_pqrsf_id',
                  table_name='site_pqrsf_responses')
    op.drop_table('site_pqrsf_responses')

    op.drop_index('ix_site_pqrsf_status', table_name='site_pqrsf')
    op.drop_index('ix_site_pqrsf_email', table_name='site_pqrsf')
    op.drop_index('ix_site_pqrsf_request_type', table_name='site_pqrsf')
    op.drop_index('ix_site_pqrsf_tracking_code', table_name='site_pqrsf')
    op.drop_table('site_pqrsf')