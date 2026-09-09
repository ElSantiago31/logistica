"""make users.email optional and purge synthetic emails

Revision ID: user_email_optional
Revises: add_advanced_event_roles
Create Date: 2026-09-09

El campo email ya no es obligatorio para usuarios staff (admins/checkin/
intendencia/web_admin) — el login es por número de documento + contraseña,
no por email. Antes, cuando no se enviaba email al crear un admin, el
backend generaba uno sintético: {documento}@logistica.local.

Esta migración:
1. Hace users.email NULLable (manteniendo UNIQUE).
2. Limpia los correos sintéticos ya existentes (los que terminan en
   @logistica.local), dejándolos en NULL para que no vuelvan a aparecer
   inventados en el panel de edición.

Los operadores (registro público) siguen teniendo email obligatorio a
nivel de API; no se tocan sus datos.
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'user_email_optional'
down_revision = 'add_advanced_event_roles'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1) Limpiar correos sintéticos ANTES de alterar la columna
    #    (más seguro: quedan en NULL y no violan UNIQUE).
    op.execute("UPDATE users SET email = NULL WHERE email LIKE '%@logistica.local'")

    # 2) Hacer la columna nullable.
    #    Nota: en SQLite alter_column con nullable requiere batch mode;
    #    en PostgreSQL (producción) funciona directo.
    op.alter_column(
        'users', 'email',
        existing_type=sa.String(255),
        nullable=True,
    )


def downgrade() -> None:
    # Revertir: volver a NOT NULL. Los NULL existentes se rellenan con el
    # patrón sintético (necesario para no violar el constraint).
    op.execute(
        "UPDATE users SET email = document_number || '@logistica.local' "
        "WHERE email IS NULL"
    )
    op.alter_column(
        'users', 'email',
        existing_type=sa.String(255),
        nullable=False,
    )