"""add is_event_only to roles + new event-only roles

Revision ID: add_event_only_roles
Revises: add_concurrency_constraints
Create Date: 2026-06-25

Cambio:
  1. Nueva columna roles.is_event_only (bool, default false).
  2. Marcar como is_event_only=true los roles de coordinacion existentes que
     NO deben aparecer en el registro de operadores (solo en creacion de evento).
  3. Insertar 3 roles nuevos exclusivos de evento.
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'add_event_only_roles'
down_revision = 'add_concurrency_constraints'
branch_labels = None
depends_on = None


# Roles existentes a marcar como event-only (no registrables)
EXISTING_EVENT_ONLY_SLUGS = [
    'coordinador_general',
    'coordinador_emergencias',
    'lider_seguridad',
    'coordinador_grupos',
]

# Roles nuevos exclusivos de evento
# (name, slug, description, hierarchy_level, area)
NEW_EVENT_ONLY_ROLES = [
    (
        'Coordinadores Externos', 'coordinadores_externos',
        'Coordinacion externa (reporta al Coordinador General)', 3, 'Externa',
    ),
    (
        'Brigadista Externo', 'brigadista_externo',
        'Brigada de emergencias externa (reporta al Coordinador General)', 3, 'Externa',
    ),
    (
        'Personal Oficina', 'personal_oficina',
        'Personal de oficina (reporta al Coordinador General)', 3, 'Oficina',
    ),
]


def upgrade() -> None:
    # 1. Agregar columna is_event_only
    op.add_column('roles', sa.Column(
        'is_event_only', sa.Boolean(), nullable=False, server_default=sa.false(),
        comment='True: rol exclusivo de eventos (no registrable por operadores)',
    ))
    op.create_index('ix_roles_is_event_only', 'roles', ['is_event_only'])

    # 2. Marcar los 4 roles existentes como event-only
    for slug in EXISTING_EVENT_ONLY_SLUGS:
        op.execute(
            sa.text("UPDATE roles SET is_event_only = true WHERE slug = :slug")
            .bindparams(slug=slug)
        )

    # 3. Insertar los 3 roles nuevos (event-only)
    for name, slug, desc, level, area in NEW_EVENT_ONLY_ROLES:
        op.execute(
            sa.text("""
                INSERT INTO roles (id, name, slug, description, hierarchy_level, area, is_event_only, is_active)
                VALUES (gen_random_uuid(), :name, :slug, :desc, :level, :area, true, true)
                ON CONFLICT (slug) DO UPDATE SET
                    name = :name, description = :desc,
                    hierarchy_level = :level, area = :area, is_event_only = true
            """).bindparams(name=name, slug=slug, desc=desc, level=level, area=area)
        )


def downgrade() -> None:
    # Borrar los 3 roles nuevos
    for _, slug, _, _, _ in NEW_EVENT_ONLY_ROLES:
        op.execute(
            sa.text("DELETE FROM roles WHERE slug = :slug").bindparams(slug=slug)
        )

    # Desmarcar los roles existentes (quitar flag)
    for slug in EXISTING_EVENT_ONLY_SLUGS:
        op.execute(
            sa.text("UPDATE roles SET is_event_only = false WHERE slug = :slug")
            .bindparams(slug=slug)
        )

    op.drop_index('ix_roles_is_event_only', table_name='roles')
    op.drop_column('roles', 'is_event_only')