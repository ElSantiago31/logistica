"""add advanced event-only roles

Revision ID: add_advanced_event_roles
Revises: add_referral_tables
Create Date: 2026-09-08

Cambio:
  Insertar 2 roles avanzados exclusivos de importación (is_event_only=true):
    - Operador Logístico Avanzada
    - Brigadista Avanzada

  Estos roles NO aparecen en el registro público ni en la edición de perfil
  del operador (esos flujos filtran is_event_only=false), pero SÍ pueden
  asignarse al importar personal desde Excel (el importador carga todos los
  roles activos) y en planes de personal de eventos.
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'add_advanced_event_roles'
down_revision = 'add_referral_tables'
branch_labels = None
depends_on = None


# Roles nuevos exclusivos de importación/eventos
# (name, slug, description, hierarchy_level, area)
ADVANCED_EVENT_ONLY_ROLES = [
    (
        'Operador Logístico Avanzada', 'operador_logistico_avanzado',
        'Operador logístico avanzado (solo asignable por importación de personal)', 3, 'Logística',
    ),
    (
        'Brigadista Avanzada', 'brigadista_avanzado',
        'Brigadista avanzado (solo asignable por importación de personal)', 3, 'Emergencias',
    ),
]


def upgrade() -> None:
    for name, slug, desc, level, area in ADVANCED_EVENT_ONLY_ROLES:
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
    for _, slug, _, _, _ in ADVANCED_EVENT_ONLY_ROLES:
        op.execute(
            sa.text("DELETE FROM roles WHERE slug = :slug").bindparams(slug=slug)
        )