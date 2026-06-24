"""add event_staff_assignments table

Revision ID: add_event_staff_assignments
Revises: add_payroll_records
Create Date: 2026-06-23

Crea tabla 'event_staff_assignments' para asignar personal del sistema
(usuarios con user_type='checkin' o 'intendencia') a eventos específicos.
Esto permite que checkin/intendencia solo vean los eventos asignados.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
import uuid


# revision identifiers, used by Alembic.
revision = 'add_event_staff_assignments'
down_revision = 'add_payroll_records'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'event_staff_assignments',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column('event_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('events.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('user_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('staff_role', sa.String(20), nullable=False, index=True,
                  comment="checkin | intendencia"),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('is_active', sa.Boolean(), default=True, nullable=False),
    )
    # Índice único: un usuario no puede ser asignado dos veces con el mismo rol al mismo evento
    op.create_index(
        'ix_event_staff_assignments_event_user_role',
        'event_staff_assignments',
        ['event_id', 'user_id', 'staff_role'],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index('ix_event_staff_assignments_event_user_role', table_name='event_staff_assignments')
    op.drop_table('event_staff_assignments')