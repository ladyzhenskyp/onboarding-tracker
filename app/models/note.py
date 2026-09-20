from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Index, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, utcnow

if TYPE_CHECKING:
    from app.models.client import Client
    from app.models.user import User


SYSTEM_NOTE_PREFIXES = ("Stage changed", "Client created")


class Note(Base):
    __tablename__ = "notes"
    __table_args__ = (Index("ix_notes_client_created", "client_id", "created_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    client_id: Mapped[int] = mapped_column(ForeignKey("clients.id", ondelete="CASCADE"))
    author_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    body: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    @property
    def is_system(self) -> bool:
        """Stage moves (services/stages.py) and client creation are logged as notes.
        They are the audit trail, so the UI shows them but does not offer to edit or delete them."""
        return self.body.startswith(SYSTEM_NOTE_PREFIXES)

    client: Mapped[Client] = relationship(back_populates="notes")
    author: Mapped[User | None] = relationship()
