"""Audit and security models."""
import uuid
from datetime import datetime
from sqlalchemy import String, Text, DateTime
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import BaseModel


class AuditLog(BaseModel):
    """Registro de auditoría de todas las acciones del sistema."""
    __tablename__ = "audit_log"

    user_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True, index=True)
    action: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    resource_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    resource_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    details: Mapped[str | None] = mapped_column(Text, nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(500), nullable=True)

    def __repr__(self):
        return f"<AuditLog {self.action} by {self.user_id}>"


class RevokedToken(BaseModel):
    """Tokens JWT revocados (logout, cambio de password)."""
    __tablename__ = "revoked_tokens"

    token_jti: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(nullable=False, index=True)
    revoked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
    )
    reason: Mapped[str | None] = mapped_column(
        String(50), nullable=True,
        comment="logout | password_change | admin_revocation",
    )

    def __repr__(self):
        return f"<RevokedToken jti={self.token_jti}>"