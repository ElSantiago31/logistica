"""Site content models — editable content for the public website.

These tables back the public homepage (SSR), the web admin panel
(``/admin/contenido``) and the public contact form. They are the single
source of truth for all marketing/content shown on the site.

Models:
    SiteSection   — key/value JSON blocks (hero, about, contact info).
    ServiceItem   — the six service cards on the homepage.
    NewsItem      — news/announcements cards.
    GalleryItem   — gallery images.
    ContactRequest — submissions from the public contact form.
"""
from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import BaseModel


class SiteSection(BaseModel):
    """Editable sections stored as a JSON-like key/value block.

    Keys: ``hero``, ``about``, ``contact``. The ``content`` column stores a
    serialized JSON string (kept simple on purpose to avoid JSONB portability
    issues between local SQLite and Postgres in production).
    """
    __tablename__ = "site_sections"

    section_key: Mapped[str] = mapped_column(
        String(50), unique=True, nullable=False, index=True,
        comment="hero | about | contact",
    )
    content: Mapped[str] = mapped_column(
        Text, nullable=False,
        comment="JSON serializado con los textos/valores de la sección",
    )

    def __repr__(self):
        return f"<SiteSection {self.section_key}>"


class ServiceItem(BaseModel):
    """A single service card on the homepage."""
    __tablename__ = "site_services"

    title: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    icon: Mapped[str | None] = mapped_column(
        String(50), nullable=True,
        comment="Identificador del ícono (emoji o nombre) usado en la UI",
    )
    image_url: Mapped[str | None] = mapped_column(String(255), nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False, index=True)

    def __repr__(self):
        return f"<ServiceItem {self.title}>"


class NewsItem(BaseModel):
    """A news/announcement entry shown on the homepage."""
    __tablename__ = "site_news"

    title: Mapped[str] = mapped_column(String(160), nullable=False)
    category: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), default="published", nullable=False, index=True,
        comment="published | draft",
    )
    image_url: Mapped[str | None] = mapped_column(String(255), nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False, index=True)

    def __repr__(self):
        return f"<NewsItem {self.title} [{self.status}]>"


class GalleryItem(BaseModel):
    """An image in the public gallery."""
    __tablename__ = "site_gallery"

    title: Mapped[str] = mapped_column(String(160), nullable=False)
    image_url: Mapped[str] = mapped_column(String(255), nullable=False)
    caption: Mapped[str | None] = mapped_column(String(255), nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False, index=True)

    def __repr__(self):
        return f"<GalleryItem {self.title}>"


class ContactRequest(BaseModel):
    """A submission from the public contact form on the homepage."""
    __tablename__ = "site_contact_requests"

    full_name: Mapped[str] = mapped_column(String(160), nullable=False)
    email: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    phone: Mapped[str | None] = mapped_column(String(40), nullable=True)
    company: Mapped[str | None] = mapped_column(String(160), nullable=True)
    event_type: Mapped[str | None] = mapped_column(String(80), nullable=True)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), default="new", nullable=False, index=True,
        comment="new | read | archived",
    )

    def __repr__(self):
        return f"<ContactRequest {self.full_name} [{self.status}]>"