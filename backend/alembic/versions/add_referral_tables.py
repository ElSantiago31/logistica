"""add referral tables

Revision ID: add_referral_tables
Revises: add_operator_id_docs
Create Date: 2026-08-27

Crea las tablas del módulo de referidos:
- referral_codes: código único por operador (generado por SuperAdmin).
- referrals: relación permanente referido → referente.
- referral_audit_logs: auditoría de acciones del módulo.
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'add_referral_tables'
down_revision = 'add_operator_id_docs'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # --- referral_codes ---
    op.create_table(
        'referral_codes',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('is_active', sa.Boolean(), server_default=sa.text('true'), nullable=False),
        sa.Column('operator_id', sa.UUID(), nullable=False),
        sa.Column('code', sa.String(length=30), nullable=False),
        sa.Column('created_by', sa.UUID(), nullable=True),
        sa.ForeignKeyConstraint(['operator_id'], ['operators.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['created_by'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('operator_id'),
        sa.UniqueConstraint('code'),
    )
    op.create_index(op.f('ix_referral_codes_operator_id'), 'referral_codes', ['operator_id'])
    op.create_index(op.f('ix_referral_codes_code'), 'referral_codes', ['code'])

    # --- referrals ---
    op.create_table(
        'referrals',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('is_active', sa.Boolean(), server_default=sa.text('true'), nullable=False),
        sa.Column('referrer_operator_id', sa.UUID(), nullable=False),
        sa.Column('referred_operator_id', sa.UUID(), nullable=False),
        sa.Column('code_used', sa.String(length=30), nullable=False),
        sa.Column('registered_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['referrer_operator_id'], ['operators.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['referred_operator_id'], ['operators.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('referred_operator_id'),
    )
    op.create_index(op.f('ix_referrals_referrer_operator_id'), 'referrals', ['referrer_operator_id'])
    op.create_index(op.f('ix_referrals_referred_operator_id'), 'referrals', ['referred_operator_id'])

    # --- referral_audit_logs ---
    op.create_table(
        'referral_audit_logs',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('is_active', sa.Boolean(), server_default=sa.text('true'), nullable=False),
        sa.Column('referrer_operator_id', sa.UUID(), nullable=True),
        sa.Column('referred_operator_id', sa.UUID(), nullable=True),
        sa.Column('user_id', sa.UUID(), nullable=True),
        sa.Column('action', sa.String(length=50), nullable=False),
        sa.Column('detail', sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(['referrer_operator_id'], ['operators.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['referred_operator_id'], ['operators.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_referral_audit_logs_referrer_operator_id'), 'referral_audit_logs', ['referrer_operator_id'])
    op.create_index(op.f('ix_referral_audit_logs_referred_operator_id'), 'referral_audit_logs', ['referred_operator_id'])
    op.create_index(op.f('ix_referral_audit_logs_action'), 'referral_audit_logs', ['action'])


def downgrade() -> None:
    op.drop_index(op.f('ix_referral_audit_logs_action'), table_name='referral_audit_logs')
    op.drop_index(op.f('ix_referral_audit_logs_referred_operator_id'), table_name='referral_audit_logs')
    op.drop_index(op.f('ix_referral_audit_logs_referrer_operator_id'), table_name='referral_audit_logs')
    op.drop_table('referral_audit_logs')
    op.drop_index(op.f('ix_referrals_referred_operator_id'), table_name='referrals')
    op.drop_index(op.f('ix_referrals_referrer_operator_id'), table_name='referrals')
    op.drop_table('referrals')
    op.drop_index(op.f('ix_referral_codes_code'), table_name='referral_codes')
    op.drop_index(op.f('ix_referral_codes_operator_id'), table_name='referral_codes')
    op.drop_table('referral_codes')