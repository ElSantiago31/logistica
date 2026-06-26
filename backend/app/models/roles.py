"""Role model - defines operator roles with hierarchy levels."""
import uuid
from sqlalchemy import String, Text, Integer, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel


class Role(BaseModel):
    """Roles de operadores: Bouncer, Acomodador, Logístico, Coordinador, etc.

    Jerarquía:
      level 1 = Coordinador General (califica a coordinadores de área)
      level 2 = Coordinador de área (califica a operadores de su área)
      level 3 = Operador (recibe calificación)
    """
    __tablename__ = "roles"

    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    slug: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    base_rate: Mapped[float | None] = mapped_column(nullable=True, comment="Tarifa base por turno")
    hierarchy_level: Mapped[int] = mapped_column(
        Integer, default=3, nullable=False, index=True,
        comment="1=Coordinador General, 2=Coordinador de área, 3=Operador",
    )
    area: Mapped[str | None] = mapped_column(
        String(50), nullable=True, index=True,
        comment="Área: Emergencias, Logística, Seguridad, etc. (None para general)",
    )
    is_event_only: Mapped[bool] = mapped_column(
        default=False, server_default=text("false"), nullable=False, index=True,
        comment="True: rol exclusivo de eventos (no registrable por operadores)",
    )

    # Relationships
    users = relationship("User", back_populates="role")
    event_staff_needs = relationship("EventStaffNeed", back_populates="role")

    def __repr__(self):
        return f"<Role {self.name}>"