"""Small write operations used by the client-detail page. Each commits."""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy.orm import Session

from app.models import Blocker, Client, Milestone, Note, User


def add_blocker(
    db: Session,
    client: Client,
    *,
    title: str,
    severity: str,
    now: datetime,
    description: str | None = None,
    owner: User | None = None,
    external_ref: str | None = None,
    milestone_id: int | None = None,
) -> Blocker:
    b = Blocker(
        client=client,
        title=title.strip(),
        description=(description or "").strip() or None,
        severity=severity,
        owner=owner,
        opened_at=now,
        external_ref=(external_ref or "").strip() or None,
        milestone_id=milestone_id,
    )
    db.add(b)
    db.commit()
    return b


def resolve_blocker(db: Session, blocker: Blocker, now: datetime) -> Blocker:
    if blocker.resolved_at is None:
        blocker.resolved_at = now
        db.commit()
    return blocker


def reopen_blocker(db: Session, blocker: Blocker) -> Blocker:
    blocker.resolved_at = None
    db.commit()
    return blocker


def add_milestone(
    db: Session,
    client: Client,
    *,
    title: str,
    due_date: date,
    owner: User | None = None,
) -> Milestone:
    m = Milestone(client=client, title=title.strip(), due_date=due_date, owner=owner)
    db.add(m)
    db.commit()
    return m


def complete_milestone(db: Session, milestone: Milestone, now: datetime) -> Milestone:
    milestone.status = "done"
    milestone.completed_at = now
    db.commit()
    return milestone


def add_note(
    db: Session, client: Client, *, body: str, now: datetime, author: User | None = None
) -> Note:
    n = Note(client=client, body=body.strip(), author=author, created_at=now)
    db.add(n)
    db.commit()
    return n
