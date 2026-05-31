"""Payroll models - evaluations, payroll records, and digital signatures."""
import uuid
from sqlalchemy import String, Text, ForeignKey, Float, Integer
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
    punctuality_score: Mapped[int] = mapped_column(Integer, nullable=False, comment="1-5")
    performance_score: Mapped[int] = mapped_column(Integer, nullable=False, comment="1-5")
    appearance_score: Mapped[int] = mapped_column(Integer, nullable=False, comment="1-5")
    attitude_score: Mapped[int] = mapped_column(Integer, nullable=False, comment="1-5")
    overall_score: Mapped[float] = mapped_column(Float, nullable=False, comment="Promedio ponderado")
    comments: Mapped[str | None] = mapped_column(Text, nullable=True)
    would_hire_again: Mapped[bool] = mapped_column(default=True, nullable=False)

    # Relationships
    event = relationship("Event")
    operator = relationship("Operator")
    evaluator = relationship("User", foreign_keys=[evaluated_by])

    def __repr__(self):
        return f"<Evaluation event={self.event_id} op={self.operator_id} score={self.overall_score}>"


class Payroll(BaseModel):
    """Registro de nómina por operador por evento."""
    __tablename__ = "payroll"

    event_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("events.id", ondelete="CASCADE"), nullable=False, index=True,
    )
    operator_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("operators.id", ondelete="CASCADE"), nullable=False, index=True,
    )
    assignment_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("event_assignments.id", ondelete="SET NULL"), nullable=True,
    )
    hours_worked: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    rate_per_hour: Mapped[float] = mapped_column(Float, nullable=False)
    total_amount: Mapped[float] = mapped_column(Float, nullable=False)
    deductions: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    net_amount: Mapped[float] = mapped_column(Float, nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), default="calculated", nullable=False, index=True,
        comment="calculated | pending_signature | signed | approved | paid",
    )
    payment_method: Mapped[str | None] = mapped_column(
        String(20), nullable=True,
        comment="cash | transfer | nequi | daviplata",
    )
    payment_reference: Mapped[str | None] = mapped_column(String(100), nullable=True)
    paid_at: Mapped[str | None] = mapped_column(String, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Relationships
    event = relationship("Event")
    operator = relationship("Operator")
    assignment = relationship("EventAssignment")
    signature = relationship("Signature", back_populates="payroll", uselist=False, cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Payroll event={self.event_id} op={self.operator_id} ${self.net_amount}>"


class Signature(BaseModel):
    """Firma digital del operador validando su nómina."""
    __tablename__ = "signatures"

    payroll_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("payroll.id", ondelete="CASCADE"), unique=True, nullable=False, index=True,
    )
    operator_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("operators.id", ondelete="CASCADE"), nullable=False, index=True,
    )
    signature_data: Mapped[str] = mapped_column(Text, nullable=False, comment="Base64 del trazo canvas")
    signature_hash: Mapped[str] = mapped_column(String(128), nullable=False, comment="SHA-256 hash de verificación")
    signed_at: Mapped[str | None] = mapped_column(String, nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)
    device_info: Mapped[str | None] = mapped_column(String(300), nullable=True)
    is_offline: Mapped[bool] = mapped_column(default=False, nullable=False)

    # Relationships
    payroll = relationship("Payroll", back_populates="signature")
    operator = relationship("Operator")

    def __repr__(self):
        return f"<Signature payroll={self.payroll_id}>"