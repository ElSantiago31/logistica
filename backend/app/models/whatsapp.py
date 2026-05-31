"""WhatsApp outbound queue model."""
import uuid
from sqlalchemy import String, Text, ForeignKey, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel


class WhatsAppOutboundQueue(BaseModel):
    """Cola de mensajes salientes de WhatsApp."""
    __tablename__ = "whatsapp_outbound_queue"

    event_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("events.id", ondelete="SET NULL"), nullable=True, index=True,
    )
    assignment_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("event_assignments.id", ondelete="SET NULL"), nullable=True,
    )
    phone_number: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    template_name: Mapped[str] = mapped_column(String(100), nullable=False)
    template_params: Mapped[str | None] = mapped_column(Text, nullable=True, comment="JSON con parámetros de la plantilla")
    message_type: Mapped[str] = mapped_column(
        String(30), default="invitation", nullable=False,
        comment="invitation | reminder_5d | reminder_1d | custom",
    )
    status: Mapped[str] = mapped_column(
        String(20), default="pending", nullable=False, index=True,
        comment="pending | sent | delivered | read | failed",
    )
    meta_message_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    max_attempts: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    sent_at: Mapped[str | None] = mapped_column(String, nullable=True)

    # Relationships
    event = relationship("Event")

    def __repr__(self):
        return f"<WAQueue {self.phone_number} status={self.status}>"