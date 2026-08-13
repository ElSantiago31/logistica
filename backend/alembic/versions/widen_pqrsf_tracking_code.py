"""widen pqrsf tracking_code to support random suffix (anti-enumeration)

Revision ID: widen_pqrsf_track
Revises: 00911dcaea23
Create Date: 2026-08-12

Amplía la columna `site_pqrsf.tracking_code` de String(20) a String(30)
para soportar el nuevo formato con sufijo aleatorio anti-enumeración:
PQR-YYYY-NNNNN-XXXX (hasta 19 caracteres, con margen).

Seguridad: los códigos previos (PQR-2026-00042) siguen siendo válidos y
únicos; no se requiere backfill porque el nuevo formato solo aplica a
PQRSF creadas a partir de este cambio.
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'widen_pqrsf_track'
down_revision = '00911dcaea23'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        'site_pqrsf', 'tracking_code',
        existing_type=sa.String(20),
        type_=sa.String(30),
        existing_nullable=False,
        existing_comment="Código público de seguimiento (ej. PQR-2026-00001-A7K2)",
    )


def downgrade() -> None:
    op.alter_column(
        'site_pqrsf', 'tracking_code',
        existing_type=sa.String(30),
        type_=sa.String(20),
        existing_nullable=False,
        existing_comment="Código público de seguimiento (ej. PQR-2026-00042)",
    )