"""Stage transitions.

Moving a client between stages touches three things that must stay consistent:
  1. close the open client_stage_history row (set exited_at),
  2. open a new history row for the destination stage,
  3. update the denormalised clients.current_stage_id.
All three happen inside one transaction; the partial unique index
ux_stage_history_open makes it impossible to end up with two open rows.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Client, ClientStageHistory, Note, Stage, User


class StageTransitionError(ValueError):
    pass


def ordered_stages(db: Session) -> list[Stage]:
    return list(db.scalars(select(Stage).order_by(Stage.sort_order)))


def next_stage(db: Session, current: Stage) -> Stage | None:
    return db.scalar(
        select(Stage).where(Stage.sort_order > current.sort_order).order_by(Stage.sort_order)
    )


def move_to_stage(
    db: Session,
    client: Client,
    to_stage: Stage,
    now: datetime,
    changed_by: User | None = None,
    reason: str | None = None,
) -> ClientStageHistory:
    """Move a client to any stage (forward or back). Commits."""
    if to_stage.id == client.current_stage_id:
        raise StageTransitionError(f"{client.name} is already in {to_stage.name}.")

    open_row = db.scalar(
        select(ClientStageHistory).where(
            ClientStageHistory.client_id == client.id,
            ClientStageHistory.exited_at.is_(None),
        )
    )
    from_name = client.current_stage.name
    if open_row is not None:
        open_row.exited_at = now

    new_row = ClientStageHistory(
        client=client, stage=to_stage, entered_at=now, changed_by=changed_by
    )
    client.current_stage = to_stage
    client.updated_at = now
    db.add(new_row)

    body = f"Stage changed: {from_name} → {to_stage.name}."
    if reason:
        body += f" {reason}"
    db.add(Note(client=client, author=changed_by, body=body, created_at=now))

    db.commit()
    db.refresh(client)
    return new_row


def advance_stage(
    db: Session, client: Client, now: datetime, changed_by: User | None = None
) -> ClientStageHistory:
    """Move to the next stage in pipeline order."""
    nxt = next_stage(db, client.current_stage)
    if nxt is None:
        raise StageTransitionError(f"{client.name} is already Live.")
    return move_to_stage(db, client, nxt, now, changed_by)
