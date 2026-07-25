"""add site content tables (sections, services, news, gallery, contact)

Revision ID: add_site_content
Revises: fix_incidents_is_active
Create Date: 2026-07-25

Crea las tablas que respaldan el contenido editable del sitio público:
  - site_sections          (hero, about, contact como JSON)
  - site_services          (tarjetas de servicios)
  - site_news              (noticias / novedades)
  - site_gallery           (galería de imágenes)
  - site_contact_requests  (envíos del formulario público de contacto)

Estas tablas son el Single Source of Truth (SSOT) para la home y el
panel /admin/contenido. Reemplazan los valores hardcodeados en home.html.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = 'add_site_content'
down_revision = 'fix_incidents_is_active'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ---------- site_sections ----------
    op.create_table(
        'site_sections',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('section_key', sa.String(50), nullable=False),
        sa.Column('content', sa.Text(), nullable=False,
                  comment="JSON serializado con los textos/valores de la sección"),
    )
    op.create_index('ix_site_sections_section_key', 'site_sections', ['section_key'], unique=True)
    op.create_index('ix_site_sections_is_active', 'site_sections', ['is_active'])

    # ---------- site_services ----------
    op.create_table(
        'site_services',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('title', sa.String(120), nullable=False),
        sa.Column('description', sa.Text(), nullable=False),
        sa.Column('icon', sa.String(50), nullable=True,
                  comment="Identificador del ícono (emoji o nombre) usado en la UI"),
        sa.Column('image_url', sa.String(255), nullable=True),
        sa.Column('sort_order', sa.Integer(), nullable=False, server_default='0'),
    )
    op.create_index('ix_site_services_sort_order', 'site_services', ['sort_order'])
    op.create_index('ix_site_services_is_active', 'site_services', ['is_active'])

    # ---------- site_news ----------
    op.create_table(
        'site_news',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('title', sa.String(160), nullable=False),
        sa.Column('category', sa.String(60), nullable=False),
        sa.Column('summary', sa.Text(), nullable=False),
        sa.Column('status', sa.String(20), nullable=False, server_default='published',
                  comment="published | draft"),
        sa.Column('image_url', sa.String(255), nullable=True),
        sa.Column('published_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('sort_order', sa.Integer(), nullable=False, server_default='0'),
    )
    op.create_index('ix_site_news_category', 'site_news', ['category'])
    op.create_index('ix_site_news_status', 'site_news', ['status'])
    op.create_index('ix_site_news_sort_order', 'site_news', ['sort_order'])

    # ---------- site_gallery ----------
    op.create_table(
        'site_gallery',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('title', sa.String(160), nullable=False),
        sa.Column('image_url', sa.String(255), nullable=False),
        sa.Column('caption', sa.String(255), nullable=True),
        sa.Column('sort_order', sa.Integer(), nullable=False, server_default='0'),
    )
    op.create_index('ix_site_gallery_sort_order', 'site_gallery', ['sort_order'])
    op.create_index('ix_site_gallery_is_active', 'site_gallery', ['is_active'])

    # ---------- site_contact_requests ----------
    op.create_table(
        'site_contact_requests',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('full_name', sa.String(160), nullable=False),
        sa.Column('email', sa.String(160), nullable=False),
        sa.Column('phone', sa.String(40), nullable=True),
        sa.Column('company', sa.String(160), nullable=True),
        sa.Column('event_type', sa.String(80), nullable=True),
        sa.Column('message', sa.Text(), nullable=False),
        sa.Column('status', sa.String(20), nullable=False, server_default='new',
                  comment="new | read | archived"),
    )
    op.create_index('ix_site_contact_requests_email', 'site_contact_requests', ['email'])
    op.create_index('ix_site_contact_requests_status', 'site_contact_requests', ['status'])


def downgrade() -> None:
    op.drop_index('ix_site_contact_requests_status', table_name='site_contact_requests')
    op.drop_index('ix_site_contact_requests_email', table_name='site_contact_requests')
    op.drop_table('site_contact_requests')

    op.drop_index('ix_site_gallery_is_active', table_name='site_gallery')
    op.drop_index('ix_site_gallery_sort_order', table_name='site_gallery')
    op.drop_table('site_gallery')

    op.drop_index('ix_site_news_sort_order', table_name='site_news')
    op.drop_index('ix_site_news_status', table_name='site_news')
    op.drop_index('ix_site_news_category', table_name='site_news')
    op.drop_table('site_news')

    op.drop_index('ix_site_services_is_active', table_name='site_services')
    op.drop_index('ix_site_services_sort_order', table_name='site_services')
    op.drop_table('site_services')

    op.drop_index('ix_site_sections_is_active', table_name='site_sections')
    op.drop_index('ix_site_sections_section_key', table_name='site_sections')
    op.drop_table('site_sections')