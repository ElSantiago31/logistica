"""Referral models - referral codes, referrals and audit log.

Flujo:
- El SuperAdmin genera un código de referido (AC-NOMBRE-XXXX) para un
  operador (el "referente", ej. Santiago).
- Un nuevo colaborador (el "referido", ej. Pepito) se registra desde la
  landing con ese código → se crea una fila en `referrals` (relación
  permanente e inmutable: un referido tiene UN solo referente).
- Las métricas del referente (personas referidas, activos, asignados,
  trabajaron) son CÁLCULO DERIVADO sobre
  `referrals` + `event_assignments`; NO se usan contadores +1/-1.
"""
import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel


class ReferralCode(BaseModel):
    """Código de referido de un operador (generado por SuperAdmin).

    `is_active` (heredado de BaseModel) indica si el código acepta NUEVOS
    registros. Deshabilitarlo NO afecta relaciones históricas.
    """
    __tablename__ = "referral_codes"

    operator_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("operators.id", ondelete="CASCADE"),
        unique=True, nullable=False, index=True,
        comment="Operador referente (único código por operador)",
    )
    code: Mapped[str] = mapped_column(
        String(30), unique=True, nullable=False, index=True,
        comment="Código público en MAYÚSCULAS, ej: AC-SANTIAGO-8F3K",
    )
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True,
        comment="Superadmin que generó el código",
    )

    # Relationships
    operator = relationship("Operator", foreign_keys=[operator_id])

    def __repr__(self):
        return f"<ReferralCode {self.code} active={self.is_active}>"


class Referral(BaseModel):
    """Relación permanente referido → referente.

    Se crea ÚNICAMENTE al momento del registro del referido (con un código
    activo). `referred_operator_id` es UNIQUE: un referido tiene un solo
    referente para siempre y no se puede cambiar ni borrar.
    """
    __tablename__ = "referrals"

    referrer_operator_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("operators.id", ondelete="CASCADE"),
        nullable=False, index=True,
        comment="Operador referente (quién comparte el código)",
    )
    referred_operator_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("operators.id", ondelete="CASCADE"),
        unique=True, nullable=False, index=True,
        comment="Operador referido (quién se registró con el código). UNIQUE.",
    )
    code_used: Mapped[str] = mapped_column(
        String(30), nullable=False,
        comment="Snapshot del código usado al registrarse",
    )
    registered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
        comment="Fecha/hora en que se registró el referido",
    )

    # Relationships
    referrer = relationship("Operator", foreign_keys=[referrer_operator_id])
    referred = relationship("Operator", foreign_keys=[referred_operator_id])

    def __repr__(self):
        return f"<Referral referrer={self.referrer_operator_id} referred={self.referred_operator_id}>"


class ReferralAuditLog(BaseModel):
    """Auditoría del módulo de referidos: quién, qué, cuándo."""
    __tablename__ = "referral_audit_logs"

    referrer_operator_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("operators.id", ondelete="SET NULL"), nullable=True, index=True,
    )
    referred_operator_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("operators.id", ondelete="SET NULL"), nullable=True, index=True,
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True,
        comment="Usuario que ejecutó la acción (superadmin o NULL si sistema/registro público)",
    )
    action: Mapped[str] = mapped_column(
        String(50), nullable=False, index=True,
        comment="code_created | code_activated | code_deactivated | referral_registered",
    )
    detail: Mapped[str | None] = mapped_column(
        Text, nullable=True,
        comment="JSON con contexto (código, email del referido, etc.)",
    )

    # Relationships
    referrer = relationship("Operator", foreign_keys=[referrer_operator_id])
    referred = relationship("Operator", foreign_keys=[referred_operator_id])
    user = relationship("User")

    def __repr__(self):
        return f"<ReferralAuditLog {self.action}>"