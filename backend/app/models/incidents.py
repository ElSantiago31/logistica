"""Incident models - operator incidents (novedades) and bans (vetos)."""
import uuid
from datetime import datetime
from sqlalchemy import String, Text, Boolean, ForeignKey, Index, text, DateTime
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel


class OperatorIncident(BaseModel):
    """Novedades registradas sobre un operador dentro de un evento.

    Cubre incidencias operativas (llegada tarde, incumplimiento, etc.) y
    también marca los vetos aplicados desde el módulo (is_veto=True).
    """
    __tablename__ = "operator_incidents"

    event_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("events.id", ondelete="CASCADE"), nullable=False, index=True,
    )
    operator_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("operators.id", ondelete="CASCADE"), nullable=False, index=True,
    )
    recorded_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True,
    )
    incident_type: Mapped[str] = mapped_column(
        String(50), nullable=False,
        comment="doble_turno | llegada_tarde | salida_anticipada | incumplimiento | "
                "llamado_atencion | observacion | otro | veto",
    )
    description: Mapped[str] = mapped_column(Text, nullable=False)
    is_veto: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False,
        comment="True si la novedad corresponde a un veto (badge rojo en historial)",
    )

    # Relationships
    event = relationship("Event", back_populates="incidents")
    operator = relationship("Operator", back_populates="incidents", foreign_keys=[operator_id])
    recorder = relationship("User", foreign_keys=[recorded_by])

    def __repr__(self):
        return f"<OperatorIncident event={self.event_id} op={self.operator_id} type={self.incident_type}>"


class OperatorBan(BaseModel):
    """Historial de vetos aplicados a un operador.

    Un operador puede ser vetado y reactivado múltiples veces; cada veto es
    una fila nueva. Solo puede existir un veto activo (is_active=True) por
    operador a la vez, garantizado por un índice único parcial.
    """
    __tablename__ = "operator_bans"
    __table_args__ = (
        # Índice único parcial: solo un veto activo por operador.
        Index(
            "uq_operator_ban_active",
            "operator_id",
            unique=True,
            postgresql_where=text("is_active = true"),
            sqlite_where=text("is_active = 1"),
        ),
    )

    operator_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("operators.id", ondelete="CASCADE"), nullable=False, index=True,
    )
    banned_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True,
    )
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    observations: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False, index=True,
        comment="True = veto vigente. False = reactivado.",
    )
    unbanned_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True,
    )
    unbanned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    unban_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Relationships
    operator = relationship("Operator", back_populates="bans", foreign_keys=[operator_id])
    banner = relationship("User", foreign_keys=[banned_by])
    unbanner = relationship("User", foreign_keys=[unbanned_by])

    def __repr__(self):
        return f"<OperatorBan op={self.operator_id} active={self.is_active} reason={self.reason[:30]}>"