from __future__ import annotations

from datetime import date, datetime
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, Date, DateTime, ForeignKey, Index, String, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, utcnow

if TYPE_CHECKING:
    from app.models.client import Client
    from app.models.user import User

MILESTONE_STATUSES = ("not_started", "in_progress", "done")


class Milestone(Base):
    __tablename__ = "milestones"
    __table_args__ = (
        CheckConstraint(
            "status IN ('not_started', 'in_progress', 'done')", name="ck_milestones_status"
        ),
        # 'done' and 'has a completion timestamp' can never disagree.
        CheckConstraint(
            "(status = 'done') = (completed_at IS NOT NULL)", name="ck_milestones_done_completed"
        ),
        Index(
            "ix_milestones_open_due",
            "due_date",
            postgresql_where=text("status <> 'done'"),
            sqlite_where=text("status <> 'done'"),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    client_id: Mapped[int] = mapped_column(ForeignKey("clients.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(200))
    due_date: Mapped[date] = mapped_column(Date)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    owner_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(20), default="not_started")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    client: Mapped[Client] = relationship(back_populates="milestones")
    owner: Mapped[User | None] = relationship()

    def is_overdue(self, today: date) -> bool:
        """Derived, never stored (see docs/schema-design.md §4)."""
        return self.status != "done" and self.due_date < today

    def __repr__(self) -> str:
        return f"<Milestone {self.id} {self.title!r} due {self.due_date}>"
