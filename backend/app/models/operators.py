"""Operator model - extended profile for operator users."""
import uuid
from sqlalchemy import String, ForeignKey, Date, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel


class Operator(BaseModel):
    """Perfil extendido de operadores con datos laborales."""
    __tablename__ = "operators"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False, index=True,
    )
    eps_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("eps.id", ondelete="SET NULL"), nullable=True,
    )
    arl_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("arl.id", ondelete="SET NULL"), nullable=True,
    )
    photo_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    photo_thumbnail_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    birth_date: Mapped[str | None] = mapped_column(Date, nullable=True)
    address: Mapped[str | None] = mapped_column(String(300), nullable=True)
    city: Mapped[str | None] = mapped_column(String(100), nullable=True)
    blood_type: Mapped[str | None] = mapped_column(String(5), nullable=True)
    emergency_contact_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    emergency_contact_phone: Mapped[str | None] = mapped_column(String(20), nullable=True)
    background_check_status: Mapped[str] = mapped_column(
        String(20), default="pending", nullable=False,
        comment="pending | approved | rejected",
    )
    background_check_date: Mapped[str | None] = mapped_column(Date, nullable=True)
    rating_avg: Mapped[float | None] = mapped_column(nullable=True, comment="Promedio de evaluaciones")
    total_events: Mapped[int] = mapped_column(default=0, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Relationships
    user = relationship("User", back_populates="operator_profile")
    eps = relationship("EPS", back_populates="operators")
    arl = relationship("ARL", back_populates="operators")
    event_assignments = relationship("EventAssignment", back_populates="operator")

    def __repr__(self):
        return f"<Operator {self.user_id}>"