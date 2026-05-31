"""EPS model - Entidad Prestadora de Salud."""
from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel


class EPS(BaseModel):
    """EPS (Entidad Prestadora de Salud) para operadores."""
    __tablename__ = "eps"

    name: Mapped[str] = mapped_column(String(200), unique=True, nullable=False)
    code: Mapped[str | None] = mapped_column(String(20), unique=True, nullable=True)
    nit: Mapped[str | None] = mapped_column(String(20), nullable=True)

    # Relationships
    operators = relationship("Operator", back_populates="eps")

    def __repr__(self):
        return f"<EPS {self.name}>"