from __future__ import annotations

from sqlalchemy import SmallInteger, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base

# Seed rows for the fixed pipeline. (key, name, sort_order)
PIPELINE_STAGES = (
    ("kickoff", "Kickoff", 1),
    ("discovery", "Discovery / Configuration", 2),
    ("uat", "UAT", 3),
    ("prod", "Prod", 4),
    ("live", "Live", 5),
)


class Stage(Base):
    """Lookup table for the ordered onboarding pipeline."""

    __tablename__ = "stages"

    id: Mapped[int] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(String(30), unique=True)
    name: Mapped[str] = mapped_column(String(60))
    sort_order: Mapped[int] = mapped_column(SmallInteger, unique=True)

    def __repr__(self) -> str:
        return f"<Stage {self.sort_order} {self.key}>"
