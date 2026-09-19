"""Header search: typeahead over client names and blocker ticket refs.

HTMX calls GET /search?q=… on every keystroke (debounced in the template) and
swaps the returned fragment into the results menu under the search box.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import or_, select
from sqlalchemy.orm import Session, selectinload

from app.deps import get_db, templates
from app.models import Blocker, Client

router = APIRouter(tags=["search"])

LIMIT = 6


@router.get("/search", name="search")
def search(
    request: Request,
    q: str = Query("", max_length=80),
    db: Session = Depends(get_db),
):
    term = q.strip()
    clients: list[Client] = []
    blockers: list[Blocker] = []
    if len(term) >= 1:
        like = f"%{term}%"
        clients = list(
            db.scalars(
                select(Client)
                .options(selectinload(Client.current_stage))
                .where(Client.name.ilike(like))
                .order_by(Client.name)
                .limit(LIMIT)
            )
        )
        blockers = list(
            db.scalars(
                select(Blocker)
                .options(selectinload(Blocker.client))
                .where(or_(Blocker.external_ref.ilike(like), Blocker.title.ilike(like)))
                .order_by(Blocker.resolved_at.is_not(None), Blocker.opened_at)
                .limit(LIMIT)
            )
        )
    return templates.TemplateResponse(
        request,
        "partials/search_results.html",
        {"q": term, "clients": clients, "blockers": blockers},
    )
