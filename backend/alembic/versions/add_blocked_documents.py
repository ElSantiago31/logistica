"""add blocked_documents table

Revision ID: add_blocked_documents
Revises: add_education_level_to_staff_needs
Create Date: 2026-06-12
"""
from alembic import op
import sqlalchemy as sa

revision = 'add_blocked_documents'
down_revision = 'add_education_level_to_staff_needs'
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.create_table(
        'blocked_documents',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('document_type', sa.String(10), nullable=False, index=True),
        sa.Column('document_number', sa.String(20), nullable=False, index=True),
        sa.Column('reason', sa.Text(), nullable=True),
        sa.Column('blocked_by', sa.String(36), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('operator_user_id', sa.String(36), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('operator_name', sa.String(201), nullable=True),
        sa.Column('is_active', sa.Boolean(), default=True, nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
    )

def downgrade() -> None:
    op.drop_table('blocked_documents')