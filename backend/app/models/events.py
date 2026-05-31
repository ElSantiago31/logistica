"""Event models - events, staff needs, and assignments."""
import uuid
from datetime import datetime
from sqlalchemy import String, Text, ForeignKey, Integer, Float, DateTime
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

    # Relationships
    event = relationship("Event", back_populates="staff_needs")
    role = relationship("Role", back_populates="event_staff_needs")

    def __repr__(self):
        return f"<EventStaffNeed event={self.event_id} role={self.role_id} qty={self.quantity_needed}>"


class EventAssignment(BaseModel):
    """Asignación de un operador a un evento con estado de confirmación."""
    __tablename__ = "event_assignments"

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
        String(20), default="invited", nullable=False, index=True,
        comment="invited | confirmed | rejected | standby | no_show | checked_in",
    )
    whatsapp_message_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    invited_at: Mapped[str | None] = mapped_column(DateTime(timezone=True), nullable=True)
    confirmed_at: Mapped[str | None] = mapped_column(DateTime(timezone=True), nullable=True)
    rejected_at: Mapped[str | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reminder_sent: Mapped[bool] = mapped_column(default=False, nullable=False)
    rate_applied: Mapped[float | None] = mapped_column(Float, nullable=True, comment="Tarifa aplicada al momento de asignación")

    # Relationships
    event = relationship("Event", back_populates="assignments")
    operator = relationship("Operator", back_populates="event_assignments")
    role = relationship("Role")

    def __repr__(self):
        return f"<EventAssignment event={self.event_id} op={self.operator_id} status={self.status}>"