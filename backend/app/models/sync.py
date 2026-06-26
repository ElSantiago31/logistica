"""Sync and attendance models for PWA offline operation."""
import uuid
from datetime import datetime
from sqlalchemy import String, ForeignKey, Integer, DateTime, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel


class SyncSession(BaseModel):
    """Sesiones de sincronización PWA (pre-evento download / post-evento upload)."""
    __tablename__ = "sync_sessions"

    event_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("events.id", ondelete="CASCADE"), nullable=False, index=True,
    )
    synced_by: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True,
    )
    session_type: Mapped[str] = mapped_column(
        String(20), nullable=False,
        comment="download (pre-event) | upload (post-event)",
    )
    status: Mapped[str] = mapped_column(
        String(20), default="pending", nullable=False,
        comment="pending | in_progress | completed | failed",
    )
    records_total: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    records_synced: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    sync_token: Mapped[str | None] = mapped_column(String(100), nullable=True, comment="Token efímero de un solo uso")
    started_at: Mapped[str | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[str | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Relationships
    event = relationship("Event")
    synced_by_user = relationship("User")

    def __repr__(self):
        return f"<SyncSession {self.session_type} event={self.event_id}>"


class AttendanceLog(BaseModel):
    """Registro de asistencia/ingreso de operadores a eventos."""
    __tablename__ = "attendance_log"
    __table_args__ = (
        UniqueConstraint(
            "event_id", "operator_id", name="uq_attendance_event_operator",
        ),
    )

    event_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("events.id", ondelete="CASCADE"), nullable=False, index=True,
    )
    operator_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("operators.id", ondelete="CASCADE"), nullable=False, index=True,
    )
    assignment_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("event_assignments.id", ondelete="SET NULL"), nullable=True,
    )
    check_in_time: Mapped[str | None] = mapped_column(DateTime(timezone=True), nullable=True)
    check_out_time: Mapped[str | None] = mapped_column(DateTime(timezone=True), nullable=True)
    check_in_method: Mapped[str] = mapped_column(
        String(20), default="manual", nullable=False,
        comment="qr | pdf417 | manual | nfc",
    )
    scanned_code: Mapped[str | None] = mapped_column(String(200), nullable=True, comment="Código QR/PDF417 escaneado")
    verified_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True,
    )
    sync_session_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("sync_sessions.id", ondelete="SET NULL"), nullable=True,
    )
    is_offline: Mapped[bool] = mapped_column(default=False, nullable=False)
    device_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    location_lat: Mapped[float | None] = mapped_column(nullable=True)
    location_lon: Mapped[float | None] = mapped_column(nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Relationships
    event = relationship("Event")
    operator = relationship("Operator")
    assignment = relationship("EventAssignment")
    verifier = relationship("User", foreign_keys=[verified_by])

    def __repr__(self):
        return f"<Attendance event={self.event_id} op={self.operator_id}>"