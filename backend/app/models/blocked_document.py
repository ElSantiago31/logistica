"""BlockedDocument model - tracks blocked operator documents to prevent re-registration."""
import uuid
from sqlalchemy import String, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel


class BlockedDocument(BaseModel):
    """Documentos bloqueados por admins - impiden re-registro."""
    __tablename__ = "blocked_documents"

    document_type: Mapped[str] = mapped_column(String(10), nullable=False, index=True)
    document_number: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    reason: Mapped[str] = mapped_column(Text, nullable=True, comment="Motivo del bloqueo")
    blocked_by: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True,
    )
    operator_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True,
        comment="ID del operador que tenía este documento",
    )
    operator_name: Mapped[str | None] = mapped_column(
        String(201), nullable=True, comment="Nombre del operador al momento del bloqueo",
    )

    # Relationship
    blocker = relationship("User", foreign_keys=[blocked_by])

    def __repr__(self):
        return f"<BlockedDocument {self.document_type} {self.document_number}>"