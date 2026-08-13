"""PQRSF models — Peticiones, Quejas, Reclamos, Sugerencias y Felicitaciones.

Estas tablas respaldan el formulario público de PQRSF en la home y la
gestión administrativa desde el panel de contenido (`/admin/contenido`).

Modelos:
    PqrsfSubmission — una PQRSF enviada por un ciudadano/cliente.
    PqrsfResponse    — historial de respuestas por email a una PQRSF.
"""
import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import BaseModel


class PqrsfSubmission(BaseModel):
    """Una PQRSF enviada desde el formulario público de la home."""
    __tablename__ = "site_pqrsf"

    tracking_code: Mapped[str] = mapped_column(
        String(20), unique=True, nullable=False, index=True,
        comment="Código público de seguimiento (ej. PQR-2026-00042)",
    )
    request_type: Mapped[str] = mapped_column(
        String(20), nullable=False, index=True,
        comment="petition | complaint | claim | suggestion | congratulation",
    )
    subject: Mapped[str] = mapped_column(String(200), nullable=False)
    full_name: Mapped[str] = mapped_column(String(160), nullable=False)
    email: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    phone: Mapped[str | None] = mapped_column(String(40), nullable=True)
    company: Mapped[str | None] = mapped_column(String(160), nullable=True)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), default="new", nullable=False, index=True,
        comment="new | in_progress | resolved | closed",
    )
    priority: Mapped[str] = mapped_column(
        String(10), default="low", nullable=False,
        comment="low | medium | high",
    )
    assigned_to: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True,
    )
    resolved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
    contacted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
        comment="Última vez que se envió una respuesta por email",
    )

    def __repr__(self):
        return f"<PqrsfSubmission {self.tracking_code} [{self.status}]>"


class PqrsfResponse(BaseModel):
    """Una respuesta (email) enviada por un admin a una PQRSF.

    Se guarda el historial completo: asunto, cuerpo, si se envió OK y
    el mensaje de error si falló el SMTP.
    """
    __tablename__ = "site_pqrsf_responses"

    pqrsf_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("site_pqrsf.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    responded_by: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=False,
    )
    subject: Mapped[str] = mapped_column(String(200), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    sent: Mapped[bool] = mapped_column(default=False, nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    def __repr__(self):
        return f"<PqrsfResponse for {self.pqrsf_id} sent={self.sent}>"