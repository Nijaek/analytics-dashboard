from __future__ import annotations

import secrets
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.base import TimestampMixin

if TYPE_CHECKING:
    from app.models.event import Event


class Project(Base, TimestampMixin):
    """Project model — one per tracked site/app."""

    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    api_key: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    domain: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Relationships
    events: Mapped[list[Event]] = relationship(
        "Event", back_populates="project", cascade="all, delete-orphan"
    )

    @staticmethod
    def generate_api_key() -> str:
        """Generate a new API key."""
        return f"proj_{secrets.token_urlsafe(32)}"
