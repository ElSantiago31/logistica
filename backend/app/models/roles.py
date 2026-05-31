"""Role model - defines operator roles."""
import uuid
from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel


class Role(BaseModel):
    """Roles de operadores: Bouncer, Acomodador, Logístico, Coordinador, etc."""
    __tablename__ = "roles"

    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    slug: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    base_rate: Mapped[float | None] = mapped_column(nullable=True, comment="Tarifa base por turno")

    # Relationships
    users = relationship("User", back_populates="role")
    event_staff_needs = relationship("EventStaffNeed", back_populates="role")

    def __repr__(self):
        return f"<Role {self.name}>"