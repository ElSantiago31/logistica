"""add password_reset_tokens table

Revision ID: add_password_reset_tokens
Revises: add_uniform_returned_at
Create Date: 2026-07-04

Crea la tabla 'password_reset_tokens' para soportar el flujo seguro de
recuperación de contraseña (CRIT-2). Reemplaza el flujo inseguro anterior
que devolvía un JWT de acceso completo en la respuesta JSON.

Seguridad:
- El 'id' (UUID opaco) que viaja al frontend NO es un JWT y no autentica.
- 'used_at' garantiza un solo uso.
- 'expires_at' limita la validez temporal.
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'add_password_reset_tokens'
down_revision = 'add_uniform_returned_at'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'password_reset_tokens',
        sa.Column('id', sa.Uuid(), primary_key=True, nullable=False),
        sa.Column('user_id', sa.Uuid(), sa.ForeignKey('users.id', ondelete='CASCADE'),
                  nullable=False, index=True, comment="Usuario que solicita el reseteo"),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False,
                  comment="Fecha de expiración del token (now + 15 min)"),
        sa.Column('used_at', sa.DateTime(timezone=True), nullable=True,
                  comment="NULL = no usado; fecha de uso = un solo uso"),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('is_active', sa.Boolean(), server_default=sa.text('true'), nullable=False),
    )
    op.create_index('ix_password_reset_tokens_user_id', 'password_reset_tokens', ['user_id'])


def downgrade() -> None:
    op.drop_index('ix_password_reset_tokens_user_id', table_name='password_reset_tokens')
    op.drop_table('password_reset_tokens')