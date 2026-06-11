"""add event_audit_logs table

Revision ID: add_event_audit_log
Revises: add_education_level
Create Date: 2026-06-11
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
import uuid

# revision identifiers
revision = 'add_event_audit_log'
down_revision = 'add_education_level'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'event_audit_logs',
        sa.Column('id', sa.String(36), primary_key=True, default=lambda: str(uuid.uuid4())),
        sa.Column('event_id', sa.String(36), sa.ForeignKey('events.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('user_id', sa.String(36), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('action', sa.String(50), nullable=False),
        sa.Column('changes', sa.Text, nullable=True),
        sa.Column('user_name', sa.String(300), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('is_active', sa.Boolean(), default=True, nullable=False),
    )
    op.create_index('ix_event_audit_logs_event_id', 'event_audit_logs', ['event_id'])


def downgrade() -> None:
    op.drop_index('ix_event_audit_logs_event_id', table_name='event_audit_logs')
    op.drop_table('event_audit_logs')