from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, utcnow

if TYPE_CHECKING:
    from app.models.client import Client
    from app.models.milestone import Milestone
    from app.models.user import User

BLOCKER_SEVERITIES = ("low", "medium", "high", "critical")


class Blocker(Base):
    __tablename__ = "blockers"
    __table_args__ = (
        CheckConstraint(
            "severity IN ('low', 'medium', 'high', 'critical')", name="ck_blockers_severity"
        ),
        CheckConstraint(
            "resolved_at IS NULL OR resolved_at >= opened_at", name="ck_blockers_dates"
        ),
        Index(
            "ix_blockers_open",
            "client_id",
            "severity",
            "opened_at",
            postgresql_where=text("resolved_at IS NULL"),
            sqlite_where=text("resolved_at IS NULL"),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    client_id: Mapped[int] = mapped_column(ForeignKey("clients.id", ondelete="CASCADE"), index=True)
    milestone_id: Mapped[int | None] = mapped_column(
        ForeignKey("milestones.id", ondelete="SET NULL"), nullable=True, index=True
    )
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    severity: Mapped[str] = mapped_column(String(10))
    owner_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    opened_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    external_ref: Mapped[str | None] = mapped_column(String(40), nullable=True)  # e.g. IMPL-142

    client: Mapped[Client] = relationship(back_populates="blockers")
    milestone: Mapped[Milestone | None] = relationship()
    owner: Mapped[User | None] = relationship()

    @property
    def is_open(self) -> bool:
        return self.resolved_at is None

    def age_days(self, now: datetime) -> int:
        end = self.resolved_at or now
        return (end - self.opened_at).days

    def __repr__(self) -> str:
        return f"<Blocker {self.id} [{self.severity}] {self.title!r}>"
