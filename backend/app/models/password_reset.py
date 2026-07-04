"""PasswordResetToken model - opaco, server-side, un solo uso.

Reemplaza el flujo inseguro anterior que devolvía un JWT de acceso completo
en la respuesta JSON de /forgot-password. Ahora se devuelve solo un UUID
opaco (reset_id) que no sirve para autenticarse en la API.
"""
import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel


class PasswordResetToken(BaseModel):
    """Tokens opacos de reseteo de contraseña (un solo uso, server-side).

    - id: UUID opaco que viaja al frontend (no es JWT, no autentica).
    - user_id: FK al usuario que solicita el reset.
    - expires_at: fecha de expiración (now + 15 min al crear).
    - used_at: NULL = no usado; set al usarlo (un solo uso).
    """
    __tablename__ = "password_reset_tokens"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Usuario que solicita el reseteo",
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        comment="Fecha de expiración del token (now + 15 min)",
    )
    used_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        default=None,
        comment="NULL = no usado; fecha de uso = un solo uso",
    )

    # Relationship
    user = relationship("User", foreign_keys=[user_id])

    def __repr__(self):
        return f"<PasswordResetToken user_id={self.user_id} used={self.used_at is not None}>"