"""Small write operations used by the client-detail page. Each commits."""

from __future__ import annotations

from datetime import date, datetime, time
from decimal import Decimal

from sqlalchemy.orm import Session

from app.models import (
    Blocker,
    Client,
    ClientStageHistory,
    Meeting,
    Milestone,
    Note,
    Stage,
    User,
)


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


# ---- edit / delete ----------------------------------------------------------------
def update_milestone(
    db: Session,
    milestone: Milestone,
    *,
    title: str,
    due_date: date,
    status: str,
    now: datetime,
    owner: User | None = None,
) -> Milestone:
    milestone.title = title.strip()
    milestone.due_date = due_date
    milestone.owner = owner
    # the table has a rule: status is "done" exactly when completed_at is set,
    # so the two are always changed together
    if status == "done" and milestone.status != "done":
        milestone.completed_at = now
    elif status != "done":
        milestone.completed_at = None
    milestone.status = status
    db.commit()
    return milestone


def delete_milestone(db: Session, milestone: Milestone) -> None:
    # blockers may point at this milestone; unlink them rather than deleting them
    for blocker in db.query(Blocker).filter(Blocker.milestone_id == milestone.id):
        blocker.milestone_id = None
    db.delete(milestone)
    db.commit()


def update_blocker(
    db: Session,
    blocker: Blocker,
    *,
    title: str,
    severity: str,
    description: str | None = None,
    owner: User | None = None,
    external_ref: str | None = None,
) -> Blocker:
    blocker.title = title.strip()
    blocker.severity = severity
    blocker.description = (description or "").strip() or None
    blocker.owner = owner
    blocker.external_ref = (external_ref or "").strip() or None
    db.commit()
    return blocker


def delete_blocker(db: Session, blocker: Blocker) -> None:
    db.delete(blocker)
    db.commit()


def update_note(db: Session, note: Note, *, body: str, author: User | None = None) -> Note:
    note.body = body.strip()
    note.author = author
    db.commit()
    return note


def delete_note(db: Session, note: Note) -> None:
    db.delete(note)
    db.commit()


# ---- meetings ---------------------------------------------------------------------
def add_meeting(
    db: Session,
    client: Client,
    *,
    held_at: datetime,
    summary: str,
    attendees: list[User],
    action_items: str | None = None,
) -> Meeting:
    m = Meeting(
        client=client,
        held_at=held_at,
        summary=summary.strip(),
        action_items=(action_items or "").strip() or None,
    )
    m.attendees = attendees
    db.add(m)
    db.commit()
    return m


def update_meeting(
    db: Session,
    meeting: Meeting,
    *,
    held_at: datetime,
    summary: str,
    attendees: list[User],
    action_items: str | None = None,
) -> Meeting:
    meeting.held_at = held_at
    meeting.summary = summary.strip()
    meeting.action_items = (action_items or "").strip() or None
    meeting.attendees = attendees
    db.commit()
    return meeting


def delete_meeting(db: Session, meeting: Meeting) -> None:
    db.delete(meeting)
    db.commit()


# ---- clients ----------------------------------------------------------------------
class ClientError(ValueError):
    """A new client can't be saved; the message is safe to show to the user."""


def create_client(
    db: Session,
    *,
    name: str,
    segment: str,
    contract_value: Decimal,
    owner: User,
    kickoff_date: date,
    target_go_live_date: date,
    stage: Stage,
    now: datetime,
) -> Client:
    """Create the client AND open its first stage-history row, in one transaction, so the
    "current stage" pointer and the history can never disagree (same rule as stage moves)."""
    name = " ".join(name.split())
    if not name:
        raise ClientError("Give the client a name.")
    if db.query(Client).filter(Client.name.ilike(name)).first():
        raise ClientError(f"There is already a client called {name}.")
    if contract_value < 0:
        raise ClientError("Contract value can't be negative.")
    if target_go_live_date < kickoff_date:
        raise ClientError("Target go-live can't be before the kickoff date.")

    # Days-in-stage counts from when the stage was entered. A client added in Kickoff entered
    # it on the kickoff date; anything else is treated as entering its stage today.
    entered = datetime.combine(kickoff_date, time(9, 0)) if stage.key == "kickoff" else now
    entered = min(entered, now)
    client = Client(
        name=name,
        segment=segment,
        contract_value=contract_value,
        owner=owner,
        kickoff_date=kickoff_date,
        target_go_live_date=target_go_live_date,
        current_stage=stage,
        created_at=now,
    )
    client.stage_history.append(
        ClientStageHistory(stage=stage, entered_at=entered, changed_by=owner)
    )
    client.notes.append(Note(body=f"Client created in {stage.name}.", author=owner, created_at=now))
    db.add(client)
    db.commit()
    return client
