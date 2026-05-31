"""ARL model - Administradora de Riesgos Laborales."""
from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel


class ARL(BaseModel):
    """ARL (Administradora de Riesgos Laborales) para operadores."""
    __tablename__ = "arl"

    name: Mapped[str] = mapped_column(String(200), unique=True, nullable=False)
    code: Mapped[str | None] = mapped_column(String(20), unique=True, nullable=True)
    nit: Mapped[str | None] = mapped_column(String(20), nullable=True)

    # Relationships
    operators = relationship("Operator", back_populates="arl")

    def __repr__(self):
        return f"<ARL {self.name}>"