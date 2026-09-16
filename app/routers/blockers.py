from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.deps import get_db, get_now, templates
from app.models import BLOCKER_SEVERITIES, Blocker, Client, User

router = APIRouter(tags=["blockers"])


@router.get("/blockers", name="blockers")
def blockers(
    request: Request,
    status: str = Query("open", pattern="^(open|closed|all)$"),
    severity: str | None = Query(None),
    owner_id: int | None = Query(None),
    client_id: int | None = Query(None),
    db: Session = Depends(get_db),
    now: datetime = Depends(get_now),
):
    stmt = select(Blocker).options(
        selectinload(Blocker.client), selectinload(Blocker.owner), selectinload(Blocker.milestone)
    )
    if status == "open":
        stmt = stmt.where(Blocker.resolved_at.is_(None))
    elif status == "closed":
        stmt = stmt.where(Blocker.resolved_at.is_not(None))
    if severity in BLOCKER_SEVERITIES:
        stmt = stmt.where(Blocker.severity == severity)
    if owner_id:
        stmt = stmt.where(Blocker.owner_id == owner_id)
    if client_id:
        stmt = stmt.where(Blocker.client_id == client_id)
    rows = list(db.scalars(stmt.order_by(Blocker.resolved_at.is_not(None), Blocker.opened_at)))

    return templates.TemplateResponse(
        request,
        "blockers.html",
        {
            "now": now,
            "rows": rows,
            "filters": {
                "status": status,
                "severity": severity,
                "owner_id": owner_id,
                "client_id": client_id,
            },
            "severities": BLOCKER_SEVERITIES,
            "users": list(db.scalars(select(User).where(User.is_active).order_by(User.name))),
            "clients": list(db.scalars(select(Client).order_by(Client.name))),
        },
    )
