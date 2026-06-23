"""Payroll models - evaluations and payroll records with signatures."""
import uuid
from datetime import datetime
from sqlalchemy import String, Text, ForeignKey, Float, DateTime, Boolean
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel


class Evaluation(BaseModel):
    """Evaluación post-evento de un operador."""
    __tablename__ = "evaluations"

    event_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("events.id", ondelete="CASCADE"), nullable=False, index=True,
    )
    operator_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("operators.id", ondelete="CASCADE"), nullable=False, index=True,
    )
    evaluated_by: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True,
    )
    punctuality_score: Mapped[int] = mapped_column(nullable=False, comment="1-5")
    performance_score: Mapped[int] = mapped_column(nullable=False, comment="1-5")
    appearance_score: Mapped[int] = mapped_column(nullable=False, comment="1-5")
    attitude_score: Mapped[int] = mapped_column(nullable=False, comment="1-5")
    overall_score: Mapped[float] = mapped_column(Float, nullable=False, comment="Promedio ponderado")
    comments: Mapped[str | None] = mapped_column(Text, nullable=True)
    would_hire_again: Mapped[bool] = mapped_column(default=True, nullable=False)

    # Relationships
    event = relationship("Event")
    operator = relationship("Operator")
    evaluator = relationship("User", foreign_keys=[evaluated_by])

    def __repr__(self):
        return f"<Evaluation event={self.event_id} op={self.operator_id} score={self.overall_score}>"


class PayrollRecord(BaseModel):
    """Registro de pago a un operador en un evento.

    Flujo: confirmed/checkin → signed (con firma del pad) → paid (con factura generada).
    La firma se almacena embebida (base64 PNG) en signature_data.
    """
    __tablename__ = "payroll_records"

    event_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("events.id", ondelete="CASCADE"), nullable=False, index=True,
    )
    operator_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("operators.id", ondelete="CASCADE"), nullable=False, index=True,
    )
    assignment_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("event_assignments.id", ondelete="SET NULL"), nullable=True, index=True,
    )

    # Snapshot del cargo y monto al momento de crear el registro
    role_name_snapshot: Mapped[str | None] = mapped_column(String(200), nullable=True)
    payment_amount: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)

    # Firma del operador (base64 PNG desde el pad de firmas)
    signature_data: Mapped[str | None] = mapped_column(Text, nullable=True, comment="Base64 PNG del trazo")

    # Estado del flujo de pago
    status: Mapped[str] = mapped_column(
        String(20), default="pending", nullable=False, index=True,
        comment="pending | signed | paid",
    )
    invoice_number: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True, comment="FAC-{año}-{contador}")

    # Metadatos de auditoría
    signed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    signed_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True,
        comment="Usuario (coordinador/admin) que presenció la firma",
    )
    paid_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True,
        comment="Usuario que generó la factura",
    )

    # Soporte offline
    is_offline: Mapped[bool] = mapped_column(default=False, nullable=False)
    device_id: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # Relationships
    event = relationship("Event")
    operator = relationship("Operator")
    assignment = relationship("EventAssignment")

    def __repr__(self):
        return f"<PayrollRecord event={self.event_id} op={self.operator_id} status={self.status}>"