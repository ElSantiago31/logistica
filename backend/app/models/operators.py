"""Operator model - extended profile for operator users."""
import math
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, String, ForeignKey, Date, Text, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel


def _as_utc_naive(dt: datetime) -> datetime:
    """Normaliza a datetime naive en UTC (algunos drivers devuelven aware)."""
    return dt.replace(tzinfo=None) if dt.tzinfo is not None else dt


class Operator(BaseModel):
    """Perfil extendido de operadores con datos laborales."""
    __tablename__ = "operators"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False, index=True,
    )
    eps_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("eps.id", ondelete="SET NULL"), nullable=True,
    )
    pension_fund_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("pension_fund.id", ondelete="SET NULL"), nullable=True,
    )
    photo_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    photo_thumbnail_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    rut_path: Mapped[str | None] = mapped_column(
        String(500), nullable=True,
        comment="Ruta del PDF del RUT comprimido (/static/rut/...)",
    )
    # Plazo para subir el RUT cuando el registro se hizo sin él (opcional).
    rut_deadline_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
        comment="Plazo (UTC) para subir el RUT tras registro sin él; NULL = RUT cargado o no aplica",
    )
    # Fotos de la cédula (frente y dorso) — obligatorias en registro, WebP comprimido
    id_document_front_path: Mapped[str | None] = mapped_column(
        String(500), nullable=True,
        comment="Ruta de la foto del documento de identidad, frente (/static/id_docs/...)",
    )
    id_document_back_path: Mapped[str | None] = mapped_column(
        String(500), nullable=True,
        comment="Ruta de la foto del documento de identidad, dorso (/static/id_docs/...)",
    )
    birth_date: Mapped[str | None] = mapped_column(Date, nullable=True)
    gender: Mapped[str | None] = mapped_column(String(20), nullable=True, comment="Género: Femenino, Masculino")
    address: Mapped[str | None] = mapped_column(String(300), nullable=True)
    city: Mapped[str | None] = mapped_column(String(100), nullable=True)
    blood_type: Mapped[str | None] = mapped_column(String(5), nullable=True)
    emergency_contact_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    emergency_contact_phone: Mapped[str | None] = mapped_column(String(20), nullable=True)
    # Experiencia y tallas
    has_protocol_experience: Mapped[bool | None] = mapped_column(Boolean, nullable=True, comment="Experiencia en protocolo")
    event_size_experience: Mapped[str | None] = mapped_column(String(50), nullable=True, comment="Tamaño evento: 100,500,1000,2000+")
    locality: Mapped[str | None] = mapped_column(String(150), nullable=True, comment="Localidad/Barrio")
    whatsapp: Mapped[str | None] = mapped_column(String(20), nullable=True, comment="Número WhatsApp")
    education_level: Mapped[str | None] = mapped_column(String(50), nullable=True, comment="Nivel de estudio: primaria,secundaria,tecnico,tecnologo,universitario,postgrado")
    shirt_size: Mapped[str | None] = mapped_column(String(10), nullable=True)
    jacket_size: Mapped[str | None] = mapped_column(String(10), nullable=True)
    background_check_status: Mapped[str] = mapped_column(
        String(20), default="pending", nullable=False,
        comment="pending | approved | rejected",
    )
    background_check_date: Mapped[str | None] = mapped_column(Date, nullable=True)
    rating_avg: Mapped[float | None] = mapped_column(nullable=True, comment="Promedio de evaluaciones")
    total_events: Mapped[int] = mapped_column(default=0, nullable=False)
    experience_roles: Mapped[str | None] = mapped_column(Text, nullable=True, comment="JSON list of role IDs with experience")
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Veto: snapshot del estado de veto para queries rápidas sin JOIN.
    is_banned: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False, index=True,
        comment="True si el operador está vetado (no puede iniciar sesión)",
    )
    # Incorporación Rápida: operador "solo evento" (usuario fantasma inactivo).
    # No aparece en directorios ni puede iniciar sesión; su limpieza corre por
    # cuenta del ciclo de vida del evento (ver app/services/quick_add.py).
    event_only: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=text("false"), nullable=False,
        comment="True: operador 'solo evento' (Incorporación Rápida). Usuario fantasma inactivo.",
    )

    # --- RUT: estado derivado (fuente única de verdad para todo el sistema) ---

    @property
    def rut_blocked(self) -> bool:
        """Sin RUT y con plazo vencido: no puede asignarse a nuevos eventos."""
        if self.rut_path or not self.rut_deadline_at:
            return False
        return datetime.utcnow() > _as_utc_naive(self.rut_deadline_at)

    @property
    def rut_days_remaining(self) -> int | None:
        """Días restantes del plazo del RUT (None si no hay plazo activo)."""
        if self.rut_path or not self.rut_deadline_at:
            return None
        remaining = _as_utc_naive(self.rut_deadline_at) - datetime.utcnow()
        return max(0, math.ceil(remaining.total_seconds() / 86400))

    # Relationships
    user = relationship("User", back_populates="operator_profile")
    eps = relationship("EPS", back_populates="operators")
    pension_fund = relationship("PensionFund", back_populates="operators")
    event_assignments = relationship(
        "EventAssignment", back_populates="operator",
        foreign_keys="EventAssignment.operator_id",
    )
    # Asignaciones donde este operador actuó como coordinador (programó/admitió)
    programmed_assignments = relationship(
        "EventAssignment", back_populates="programmed_by_operator",
        foreign_keys="EventAssignment.programmed_by_operator_id",
    )
    admitted_assignments = relationship(
        "EventAssignment", back_populates="admitted_by_operator",
        foreign_keys="EventAssignment.admitted_by_operator_id",
    )
    # Novedades y vetos del operador
    incidents = relationship(
        "OperatorIncident", back_populates="operator",
        foreign_keys="OperatorIncident.operator_id", cascade="all, delete-orphan",
    )
    bans = relationship(
        "OperatorBan", back_populates="operator",
        foreign_keys="OperatorBan.operator_id", cascade="all, delete-orphan",
    )

    def __repr__(self):
        return f"<Operator {self.user_id}>"