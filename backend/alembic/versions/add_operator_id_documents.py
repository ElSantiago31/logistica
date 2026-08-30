"""add operator id document photos (front/back) to operators

Revision ID: add_operator_id_docs
Revises: widen_pqrsf_track
Create Date: 2026-08-26

Agrega las columnas `operators.id_document_front_path` e
`operators.id_document_back_path` para almacenar las fotos de la cédula
(frente y dorso) que el operador debe subir en el registro, comprimidas
a WebP (color, máx 1400px, calidad 70) — típico 100-250KB por lado.

Nullable: los operadores ya registrados quedan NULL (solo aplica al
flujo de registro nuevo); los admins ven "Sin cédula" hasta que el
operador vuelva a enviar documentos.
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'add_operator_id_docs'
down_revision = 'widen_pqrsf_track'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        'operators',
        sa.Column(
            'id_document_front_path',
            sa.String(500),
            nullable=True,
            comment='Ruta de la foto del documento de identidad, frente (/static/id_docs/...)',
        ),
    )
    op.add_column(
        'operators',
        sa.Column(
            'id_document_back_path',
            sa.String(500),
            nullable=True,
            comment='Ruta de la foto del documento de identidad, dorso (/static/id_docs/...)',
        ),
    )


def downgrade() -> None:
    op.drop_column('operators', 'id_document_back_path')
    op.drop_column('operators', 'id_document_front_path')