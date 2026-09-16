from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, utcnow

if TYPE_CHECKING:
    from app.models.blocker import Blocker
    from app.models.meeting import Meeting
    from app.models.milestone import Milestone
    from app.models.note import Note
    from app.models.stage import Stage
    from app.models.user import User

CLIENT_SEGMENTS = ("enterprise", "mid_market", "smb")


class Client(Base):
    __tablename__ = "clients"
    __table_args__ = (
        CheckConstraint(
            "segment IN ('enterprise', 'mid_market', 'smb')", name="ck_clients_segment"
        ),
        CheckConstraint("contract_value >= 0", name="ck_clients_contract_value"),
        CheckConstraint(
            "target_go_live_date >= kickoff_date", name="ck_clients_go_live_after_kickoff"
        ),
        Index("ix_clients_target_go_live", "target_go_live_date"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(160), unique=True)
    segment: Mapped[str] = mapped_column(String(20))
    contract_value: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    kickoff_date: Mapped[date] = mapped_column(Date)
    target_go_live_date: Mapped[date] = mapped_column(Date)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    # Denormalised pointer to the open stage-history row (see docs/schema-design.md §3).
    current_stage_id: Mapped[int] = mapped_column(ForeignKey("stages.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)

    owner: Mapped[User] = relationship(back_populates="clients")
    current_stage: Mapped[Stage] = relationship()
    stage_history: Mapped[list[ClientStageHistory]] = relationship(
        back_populates="client",
        cascade="all, delete-orphan",
        order_by="ClientStageHistory.entered_at",
    )
    milestones: Mapped[list[Milestone]] = relationship(
        back_populates="client", cascade="all, delete-orphan", order_by="Milestone.due_date"
    )
    blockers: Mapped[list[Blocker]] = relationship(
        back_populates="client", cascade="all, delete-orphan", order_by="Blocker.opened_at"
    )
    notes: Mapped[list[Note]] = relationship(
        back_populates="client", cascade="all, delete-orphan", order_by="Note.created_at.desc()"
    )
    meetings: Mapped[list[Meeting]] = relationship(
        back_populates="client", cascade="all, delete-orphan", order_by="Meeting.held_at.desc()"
    )

    def __repr__(self) -> str:
        return f"<Client {self.id} {self.name}>"


class ClientStageHistory(Base):
    """One row per stage visit. exited_at IS NULL marks the current stage."""

    __tablename__ = "client_stage_history"
    __table_args__ = (
        CheckConstraint(
            "exited_at IS NULL OR exited_at >= entered_at", name="ck_stage_history_dates"
        ),
        # Exactly one open row per client (partial unique index on both dialects).
        Index(
            "ux_stage_history_open",
            "client_id",
            unique=True,
            postgresql_where=text("exited_at IS NULL"),
            sqlite_where=text("exited_at IS NULL"),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    client_id: Mapped[int] = mapped_column(ForeignKey("clients.id", ondelete="CASCADE"), index=True)
    stage_id: Mapped[int] = mapped_column(ForeignKey("stages.id"), index=True)
    entered_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    exited_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    changed_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)

    client: Mapped[Client] = relationship(back_populates="stage_history")
    stage: Mapped[Stage] = relationship()
    changed_by: Mapped[User | None] = relationship()

    def __repr__(self) -> str:
        day = f"{self.entered_at:%Y-%m-%d}"
        return f"<StageHistory client={self.client_id} stage={self.stage_id} {day}>"
