from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Column, DateTime, ForeignKey, Index, Table, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, utcnow

if TYPE_CHECKING:
    from app.models.client import Client
    from app.models.user import User

# Junction table for the many-to-many between meetings and users.
meeting_attendees = Table(
    "meeting_attendees",
    Base.metadata,
    Column("meeting_id", ForeignKey("meetings.id", ondelete="CASCADE"), primary_key=True),
    Column("user_id", ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
    Index("ix_meeting_attendees_user_id", "user_id"),
)


class Meeting(Base):
    __tablename__ = "meetings"
    __table_args__ = (Index("ix_meetings_client_held", "client_id", "held_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    client_id: Mapped[int] = mapped_column(ForeignKey("clients.id", ondelete="CASCADE"))
    held_at: Mapped[datetime] = mapped_column(DateTime)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    action_items: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    client: Mapped[Client] = relationship(back_populates="meetings")
    attendees: Mapped[list[User]] = relationship(secondary=meeting_attendees)
