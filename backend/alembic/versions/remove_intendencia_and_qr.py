"""Remove intendencia role and QR scanner flow.

Migración que:
1. Convierte todos los usuarios user_type='intendencia' → 'checkin'.
2. Desduplica event_staff_assignments (un usuario no puede tener dos staff_role
   para el mismo evento) y convierte staff_role='intendencia' → 'checkin'.
3. Limpia el histórico de QR: check_in_method='qr' → 'manual'.
4. Elimina la columna attendance_log.scanned_code (ya no se usa sin escáner QR).

Revision ID: rm_intendencia_qr
Revises: add_rut_to_operators
Create Date: 2026-07-10
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'rm_intendencia_qr'
down_revision = 'add_rut_to_operators'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1) Convertir usuarios intendencia → checkin
    op.execute(
        "UPDATE users SET user_type = 'checkin' WHERE user_type = 'intendencia'"
    )

    # 2) Desduplicar event_staff_assignments antes del update de staff_role.
    #    Si un usuario tiene filas 'checkin' E 'intendencia' para el mismo evento,
    #    eliminamos la fila 'intendencia' (la 'checkin' tiene prioridad) para que
    #    el UPDATE posterior no viole la restricción UNIQUE(event_id, user_id).
    op.execute(
        """
        DELETE FROM event_staff_assignments a
        USING event_staff_assignments b
        WHERE a.event_id = b.event_id
          AND a.user_id = b.user_id
          AND a.staff_role = 'intendencia'
          AND b.staff_role = 'checkin'
        """
    )
    # Ahora sí: convertir el resto de intendencia → checkin
    op.execute(
        "UPDATE event_staff_assignments SET staff_role = 'checkin' "
        "WHERE staff_role = 'intendencia'"
    )

    # 3) Limpiar histórico QR: ya no hay escáner, todo es manual
    op.execute(
        "UPDATE attendance_log SET check_in_method = 'manual' "
        "WHERE check_in_method = 'qr'"
    )

    # 4) Eliminar la columna scanned_code (datos de QR/PDF417 escaneados)
    op.drop_column('attendance_log', 'scanned_code')


def downgrade() -> None:
    # 4) Recrear la columna scanned_code
    op.add_column(
        'attendance_log',
        sa.Column(
            'scanned_code',
            sa.String(length=200),
            nullable=True,
            comment="Código QR/PDF417 escaneado",
        ),
    )
    # Nota: no se puede revertir el UPDATE de check_in_method ni los cambios
    # de user_type/staff_role sin información adicional (no sabemos cuáles
    # eran intendencia originalmente), así que el downgrade solo restaura
    # la estructura de la columna.