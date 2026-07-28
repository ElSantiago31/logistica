"""add site_stages table (Grandes Escenarios)

Revision ID: add_site_stages
Revises: add_site_content
Create Date: 2026-07-27

Crea la tabla `site_stages` que respalda la sección 'Grandes Escenarios'
de la home pública. Cada registro representa un evento/artista/escenario
destacado con imagen de fondo, label (eyebrow) y título.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = 'add_site_stages'
down_revision = 'add_site_content'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'site_stages',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('label', sa.String(80), nullable=False,
                  comment="Texto pequeño (eyebrow): ej. 'Artista internacional'"),
        sa.Column('title', sa.String(160), nullable=False,
                  comment="Texto fuerte: ej. 'J Balvin'"),
        sa.Column('image_url', sa.String(255), nullable=False),
        sa.Column('sort_order', sa.Integer(), nullable=False, server_default='0'),
    )
    op.create_index('ix_site_stages_sort_order', 'site_stages', ['sort_order'])
    op.create_index('ix_site_stages_is_active', 'site_stages', ['is_active'])


def downgrade() -> None:
    op.drop_index('ix_site_stages_is_active', table_name='site_stages')
    op.drop_index('ix_site_stages_sort_order', table_name='site_stages')
    op.drop_table('site_stages')