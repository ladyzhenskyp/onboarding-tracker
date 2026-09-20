"""Calendar: every client meeting across the team, one month at a time.

The month and the optional team-member filter are query parameters, so any view is a
shareable URL (same idea as Insights).
"""

from __future__ import annotations

import calendar as cal
from datetime import date, datetime, timedelta

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.deps import get_db, get_now, opt_int, templates
from app.models import Meeting, User

router = APIRouter(tags=["calendar"])


def _month_start(raw: str | None, today: date) -> date:
    """ "2026-09" -> date(2026, 9, 1); anything missing or malformed means this month."""
    try:
        year, month = (int(p) for p in (raw or "").split("-"))
        return date(year, month, 1)
    except (ValueError, TypeError):
        return today.replace(day=1)


@router.get("/calendar", name="calendar")
def calendar_page(
    request: Request,
    month: str | None = Query(None),
    person_id: str | None = Query(None),
    db: Session = Depends(get_db),
    now: datetime = Depends(get_now),
):
    today = now.date()
    first = _month_start(month, today)
    # whole weeks, Monday to Sunday, covering the month
    weeks = cal.Calendar(firstweekday=0).monthdatescalendar(first.year, first.month)
    grid_start, grid_end = weeks[0][0], weeks[-1][-1]

    stmt = (
        select(Meeting)
        .options(selectinload(Meeting.client), selectinload(Meeting.attendees))
        .where(
            Meeting.held_at >= datetime.combine(grid_start, datetime.min.time()),
            Meeting.held_at < datetime.combine(grid_end + timedelta(days=1), datetime.min.time()),
        )
        .order_by(Meeting.held_at)
    )
    person = opt_int(person_id)
    if person:
        stmt = stmt.where(Meeting.attendees.any(User.id == person))
    meetings = list(db.scalars(stmt))

    by_day: dict[date, list[Meeting]] = {}
    for m in meetings:
        by_day.setdefault(m.held_at.date(), []).append(m)

    prev_month = (first - timedelta(days=1)).replace(day=1)
    next_month = (first + timedelta(days=32)).replace(day=1)
    agenda = [m for m in meetings if today <= m.held_at.date() <= today + timedelta(days=7)]

    return templates.TemplateResponse(
        request,
        "calendar.html",
        {
            "now": now,
            "today": today,
            "first": first,
            "weeks": weeks,
            "by_day": by_day,
            "in_month": sum(1 for m in meetings if m.held_at.month == first.month),
            "agenda": agenda,
            "prev": prev_month.strftime("%Y-%m"),
            "next": next_month.strftime("%Y-%m"),
            "this_month": today.strftime("%Y-%m"),
            "users": list(db.scalars(select(User).where(User.is_active).order_by(User.name))),
            "person_id": person,
        },
    )
