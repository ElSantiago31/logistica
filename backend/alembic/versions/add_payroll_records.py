"""add payroll_records table, drop old payroll + signatures

Revision ID: add_payroll_records
Revises: add_operator_gender
Create Date: 2026-06-21

Reestructura el módulo de Nómina:
- Crea tabla nueva 'payroll_records' (pago + firma embebida + factura)
- Elimina tablas viejas 'signatures' y 'payroll' (código legacy)
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
import uuid


# revision identifiers, used by Alembic.
revision = 'add_payroll_records'
down_revision = 'add_operator_gender'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1) Crear tabla nueva payroll_records
    op.create_table(
        'payroll_records',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column('event_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('events.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('operator_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('operators.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('assignment_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('event_assignments.id', ondelete='SET NULL'), nullable=True, index=True),
        sa.Column('role_name_snapshot', sa.String(200), nullable=True),
        sa.Column('payment_amount', sa.Float(), nullable=False, server_default='0'),
        sa.Column('signature_data', sa.Text(), nullable=True,
                  comment='Base64 PNG del trazo'),
        sa.Column('status', sa.String(20), nullable=False, server_default='pending', index=True,
                  comment='pending | signed | paid'),
        sa.Column('invoice_number', sa.String(50), nullable=True, index=True,
                  comment='FAC-{año}-{contador}'),
        sa.Column('signed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('paid_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('signed_by', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('paid_by', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('is_offline', sa.Boolean(), default=False, nullable=False),
        sa.Column('device_id', sa.String(100), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('is_active', sa.Boolean(), default=True, nullable=False),
    )

    # 2) Eliminar tablas viejas del sistema de nómina anterior
    op.drop_table('signatures')
    op.drop_table('payroll')


def downgrade() -> None:
    # Recrear tablas viejas (para rollback)
    op.create_table(
        'payroll',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column('event_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('events.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('operator_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('operators.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('assignment_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('event_assignments.id', ondelete='SET NULL'), nullable=True),
        sa.Column('hours_worked', sa.Float(), nullable=False, server_default='0'),
        sa.Column('rate_per_hour', sa.Float(), nullable=False),
        sa.Column('total_amount', sa.Float(), nullable=False),
        sa.Column('deductions', sa.Float(), server_default='0', nullable=False),
        sa.Column('net_amount', sa.Float(), nullable=False),
        sa.Column('status', sa.String(20), server_default='calculated', nullable=False, index=True),
        sa.Column('payment_method', sa.String(20), nullable=True),
        sa.Column('payment_reference', sa.String(100), nullable=True),
        sa.Column('paid_at', sa.String(), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('is_active', sa.Boolean(), default=True, nullable=False),
    )
    op.create_table(
        'signatures',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column('payroll_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('payroll.id', ondelete='CASCADE'), unique=True, nullable=False, index=True),
        sa.Column('operator_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('operators.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('signature_data', sa.Text(), nullable=False),
        sa.Column('signature_hash', sa.String(128), nullable=False),
        sa.Column('signed_at', sa.String(), nullable=True),
        sa.Column('ip_address', sa.String(45), nullable=True),
        sa.Column('device_info', sa.String(300), nullable=True),
        sa.Column('is_offline', sa.Boolean(), default=False, nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('is_active', sa.Boolean(), default=True, nullable=False),
    )
    op.drop_table('payroll_records')