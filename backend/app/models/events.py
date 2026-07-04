"""Event models - events, staff needs, and assignments."""
import uuid
from datetime import datetime
from sqlalchemy import String, Text, ForeignKey, Integer, Float, DateTime, Index, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel


class Event(BaseModel):
    """Eventos configurados por coordinadores."""
    __tablename__ = "events"

    name: Mapped[str] = mapped_column(String(300), nullable=False)
    slug: Mapped[str | None] = mapped_column(String(100), unique=True, nullable=True, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    location: Mapped[str] = mapped_column(String(500), nullable=False)
    address: Mapped[str | None] = mapped_column(String(500), nullable=True)
    city: Mapped[str | None] = mapped_column(String(100), nullable=True)
    start_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    end_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    setup_date: Mapped[str | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(
        String(20), default="draft", nullable=False, index=True,
        comment="draft | published | in_progress | completed | cancelled",
    )
    created_by: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True,
    )
    client_name: Mapped[str | None] = mapped_column(String(300), nullable=True)
    client_phone: Mapped[str | None] = mapped_column(String(20), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Relationships
    creator = relationship("User", foreign_keys=[created_by])
    staff_needs = relationship("EventStaffNeed", back_populates="event", cascade="all, delete-orphan")
    assignments = relationship("EventAssignment", back_populates="event", cascade="all, delete-orphan")
    staff_assignments = relationship("EventStaffAssignment", back_populates="event", cascade="all, delete-orphan")
    audit_logs = relationship("EventAuditLog", back_populates="event", cascade="all, delete-orphan", order_by="desc(EventAuditLog.created_at)")
    coordinator_quotas = relationship("EventCoordinatorQuota", back_populates="event", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Event {self.name} ({self.status})>"


class EventStaffNeed(BaseModel):
    """Cuotas de personal por rol para un evento."""
    __tablename__ = "event_staff_needs"

    event_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("events.id", ondelete="CASCADE"), nullable=False, index=True,
    )
    role_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("roles.id", ondelete="CASCADE"), nullable=False, index=True,
    )
    quantity_needed: Mapped[int] = mapped_column(Integer, nullable=False)
    quantity_confirmed: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    rate_per_shift: Mapped[float | None] = mapped_column(Float, nullable=True, comment="Tarifa para este evento/rol")
    education_level: Mapped[str | None] = mapped_column(
        String(50), nullable=True,
        comment="Nivel educativo minimo requerido: primaria,secundaria,tecnico,tecnologo,universitario,postgrado",
    )

    # Relationships
    event = relationship("Event", back_populates="staff_needs")
    role = relationship("Role", back_populates="event_staff_needs")

    def __repr__(self):
        return f"<EventStaffNeed event={self.event_id} role={self.role_id} qty={self.quantity_needed}>"


class EventAuditLog(BaseModel):
    """Log de cambios en eventos - quién, qué, cuándo."""
    __tablename__ = "event_audit_logs"

    event_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("events.id", ondelete="CASCADE"), nullable=False, index=True,
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True,
    )
    action: Mapped[str] = mapped_column(
        String(50), nullable=False,
        comment="created | updated | status_changed | staff_updated | deleted",
    )
    changes: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="JSON con los campos que cambiaron",
    )
    user_name: Mapped[str | None] = mapped_column(String(300), nullable=True)

    # Relationships
    event = relationship("Event", back_populates="audit_logs")
    user = relationship("User")

    def __repr__(self):
        return f"<EventAuditLog event={self.event_id} action={self.action}>"


class EventAssignment(BaseModel):
    """Asignación de un operador a un evento con estado de confirmación."""
    __tablename__ = "event_assignments"
    # Constraints parciales únicos (un solo uniform por evento).
    # Funciona en PostgreSQL (postgresql_where) y SQLite (sqlite_where).
    # El constraint solo aplica cuando el número no es NULL, permitiendo
    # múltiples filas sin indumentaria asignada.
    __table_args__ = (
        Index(
            "uq_assignment_shirt_event",
            "event_id", "shirt_number",
            unique=True,
            postgresql_where=text("shirt_number IS NOT NULL"),
            sqlite_where=text("shirt_number IS NOT NULL"),
        ),
        Index(
            "uq_assignment_jacket_event",
            "event_id", "jacket_number",
            unique=True,
            postgresql_where=text("jacket_number IS NOT NULL"),
            sqlite_where=text("jacket_number IS NOT NULL"),
        ),
        Index(
            "uq_assignment_cap_event",
            "event_id", "cap_number",
            unique=True,
            postgresql_where=text("cap_number IS NOT NULL"),
            sqlite_where=text("cap_number IS NOT NULL"),
        ),
    )

    event_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("events.id", ondelete="CASCADE"), nullable=False, index=True,
    )
    operator_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("operators.id", ondelete="CASCADE"), nullable=False, index=True,
    )
    role_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("roles.id", ondelete="SET NULL"), nullable=True,
    )
    status: Mapped[str] = mapped_column(
        String(30), default="invited", nullable=False, index=True,
        comment="invited | confirmed | rejected | standby | no_show | checked_in | sin_acreditacion",
    )
    whatsapp_message_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    invited_at: Mapped[str | None] = mapped_column(DateTime(timezone=True), nullable=True)
    confirmed_at: Mapped[str | None] = mapped_column(DateTime(timezone=True), nullable=True)
    rejected_at: Mapped[str | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reminder_sent: Mapped[bool] = mapped_column(default=False, nullable=False)
    rate_applied: Mapped[float | None] = mapped_column(Float, nullable=True, comment="Tarifa aplicada al momento de asignación")
    # Coordinador que programó al operador (del formulario de registro)
    programmed_by: Mapped[str | None] = mapped_column(
        String(100), nullable=True,
        comment="Coordinador que programó al operador (del formulario de inyección)",
    )
    # Coordinador que ADMITE al operador (el cupo se descuenta de acá).
    # Por defecto es igual a programmed_by, pero puede cambiar si un
    # coordinador se llena y el operador se reasigna a otro.
    admitted_by: Mapped[str | None] = mapped_column(
        String(100), nullable=True,
        comment="Coordinador que admitió al operador (cupo). Default = programmed_by",
    )
    # FK al operador-coordinador que programó / admitió (nuevo flujo de cupos).
    programmed_by_operator_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("operators.id", ondelete="SET NULL"), nullable=True, index=True,
        comment="Operador-coordinador que programó a este operador en el evento",
    )
    admitted_by_operator_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("operators.id", ondelete="SET NULL"), nullable=True, index=True,
        comment="Operador-coordinador que admitió a este operador (cupo). Default = programmed_by",
    )
    # Uniform assignment fields
    shirt_number: Mapped[str | None] = mapped_column(String(20), nullable=True, comment="Número de camisa asignada")
    jacket_number: Mapped[str | None] = mapped_column(String(20), nullable=True, comment="Número de chaqueta asignada")
    cap_number: Mapped[str | None] = mapped_column(String(20), nullable=True, comment="Número de gorra asignada")
    # Fecha de devolución de uniforme (NULL = pendiente de devolución)
    uniform_returned_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
        comment="Fecha/hora de devolución de uniforme. NULL = pendiente.",
    )

    # Relationships
    event = relationship("Event", back_populates="assignments")
    operator = relationship("Operator", back_populates="event_assignments", foreign_keys=[operator_id])
    role = relationship("Role")
    programmed_by_operator = relationship("Operator", foreign_keys=[programmed_by_operator_id])
    admitted_by_operator = relationship("Operator", foreign_keys=[admitted_by_operator_id])

    def __repr__(self):
        return f"<EventAssignment event={self.event_id} op={self.operator_id} status={self.status}>"


class EventStaffAssignment(BaseModel):
    """Asignación de personal del sistema (checkin/intendencia) a un evento.

    Permite que usuarios con user_type='checkin' o 'intendencia' solo vean
    los eventos donde el superadmin los asignó explícitamente.
    """
    __tablename__ = "event_staff_assignments"

    event_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("events.id", ondelete="CASCADE"), nullable=False, index=True,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True,
    )
    staff_role: Mapped[str] = mapped_column(
        String(20), nullable=False, index=True,
        comment="checkin | intendencia",
    )

    # Relationships
    event = relationship("Event", back_populates="staff_assignments")
    user = relationship("User")

    def __repr__(self):
        return f"<EventStaffAssignment event={self.event_id} user={self.user_id} role={self.staff_role}>"


class EventCoordinatorQuota(BaseModel):
    """Cupo de operadores que un coordinador gestiona en un evento.

    Nuevo flujo (eventos nuevos): el superadmin selecciona operadores del
    listado como coordinadores y les asigna un cupo. El cupo es solo
    informativo (no bloquea la asignación: un coordinador puede asignar
    más operadores que su cupo).

    Flujo legacy (Futbolfest etc.): coordinador identificado por nombre en
    MAYÚSCULAS (sin FK). Se conserva para no romper datos existentes.
    """
    __tablename__ = "event_coordinator_quotas"
    __table_args__ = (
        # Índice único para el flujo legacy (nombre string).
        Index(
            "uq_event_coordinator",
            "event_id", "coordinator",
            unique=True,
            postgresql_where=text("coordinator_operator_id IS NULL"),
            sqlite_where=text("coordinator_operator_id IS NULL"),
        ),
        # Índice único para el nuevo flujo (FK a operador).
        Index(
            "uq_event_coordinator_operator",
            "event_id", "coordinator_operator_id",
            unique=True,
            postgresql_where=text("coordinator_operator_id IS NOT NULL"),
            sqlite_where=text("coordinator_operator_id IS NOT NULL"),
        ),
    )

    event_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("events.id", ondelete="CASCADE"), nullable=False, index=True,
    )
    # Nombre del coordinador en MAYÚSCULAS (ej: XIMENA, CLAUDIA, SANDRA).
    # Para el nuevo flujo se llena automáticamente desde el operador (display).
    coordinator: Mapped[str] = mapped_column(
        String(100), nullable=False,
        comment="Nombre del coordinador en MAYÚSCULAS (display)",
    )
    # FK al operador-coordinador (nuevo flujo). NULL en datos legacy.
    coordinator_operator_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("operators.id", ondelete="SET NULL"), nullable=True, index=True,
        comment="Operador-coordinador (nuevo flujo). NULL en datos legacy.",
    )
    quota: Mapped[int] = mapped_column(Integer, nullable=False, comment="Cupo (informativo, no bloquea)")

    # Relationships
    event = relationship("Event", back_populates="coordinator_quotas")
    coordinator_operator = relationship("Operator", foreign_keys=[coordinator_operator_id])

    def __repr__(self):
        return f"<EventCoordinatorQuota event={self.event_id} coord={self.coordinator} quota={self.quota}>"
