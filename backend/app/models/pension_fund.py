"""PensionFund model - Fondo de Pensión del operador."""
from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel


class PensionFund(BaseModel):
    """Fondo de Pensión (administradora) para operadores."""
    __tablename__ = "pension_fund"

    name: Mapped[str] = mapped_column(String(200), unique=True, nullable=False)
    code: Mapped[str | None] = mapped_column(String(20), unique=True, nullable=True)
    nit: Mapped[str | None] = mapped_column(String(20), nullable=True)

    # Relationships
    operators = relationship("Operator", back_populates="pension_fund")

    def __repr__(self):
        return f"<PensionFund {self.name}>"