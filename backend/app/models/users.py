"""User model - all system users (superadmin, coordinators, operators)."""
import uuid
from sqlalchemy import String, Boolean, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel


class User(BaseModel):
    """Usuarios del sistema: Superadmin, Coordinador, Operador."""
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    first_name: Mapped[str] = mapped_column(String(100), nullable=False)
    last_name: Mapped[str] = mapped_column(String(100), nullable=False)
    phone: Mapped[str | None] = mapped_column(String(20), nullable=True, index=True)
    document_number: Mapped[str | None] = mapped_column(String(20), nullable=True, unique=True, index=True)
    document_type: Mapped[str] = mapped_column(String(10), default="CC", nullable=False)
    user_type: Mapped[str] = mapped_column(
        String(20), nullable=False, index=True,
        comment="superadmin | coordinator | operator",
    )
    role_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("roles.id", ondelete="SET NULL"), nullable=True,
    )
    is_verified: Mapped[bool] = mapped_column(default=False, nullable=False)
    is_approved: Mapped[bool] = mapped_column(default=False, nullable=False)
    last_login: Mapped[str | None] = mapped_column(String, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Relationships
    role = relationship("Role", back_populates="users")
    operator_profile = relationship("Operator", back_populates="user", uselist=False, cascade="all, delete-orphan")

    def __repr__(self):
        return f"<User {self.email} ({self.user_type})>"

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}"