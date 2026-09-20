"""Insights: the analytical view (charts + aggregate tables).

The dashboard is for triage and stays short; anything "how are we doing over
time / across owners" lives here. Filters are plain query parameters so any
view is a shareable URL, and every number on the page is computed from the same
filtered set of accounts.
"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.deps import get_db, get_now, get_risk_config, opt_date, opt_int, templates
from app.models import CLIENT_SEGMENTS, Blocker, User
from app.services import queries as q
from app.services.risk import RiskConfig
from app.services.stages import ordered_stages

router = APIRouter(tags=["insights"])


def _short(stage_name: str) -> str:
    """Axis-friendly stage label."""
    return stage_name.split(" / ")[0]


@router.get("/insights", name="insights")
def insights(
    request: Request,
    owner_id: str | None = Query(None),
    segment: str | None = Query(None),
    stage: str | None = Query(None),
    kickoff_from: str | None = Query(None),
    kickoff_to: str | None = Query(None),
    db: Session = Depends(get_db),
    now: datetime = Depends(get_now),
    cfg: RiskConfig = Depends(get_risk_config),
):
    # the form sends untouched filters as "", so parse leniently (see deps.opt_int)
    owner_id, kickoff_from, kickoff_to = (
        opt_int(owner_id),
        opt_date(kickoff_from),
        opt_date(kickoff_to),
    )
    stages = ordered_stages(db)
    health = q.client_health(db, now, cfg)

    # ---- apply filters (in Python: the set is small and already loaded for the rules)
    rows = health
    if owner_id:
        rows = [h for h in rows if h.client.owner_id == owner_id]
    if segment in CLIENT_SEGMENTS:
        rows = [h for h in rows if h.client.segment == segment]
    if stage:
        rows = [h for h in rows if h.client.current_stage.key == stage]
    if kickoff_from:
        rows = [h for h in rows if h.client.kickoff_date >= kickoff_from]
    if kickoff_to:
        rows = [h for h in rows if h.client.kickoff_date <= kickoff_to]
    ids = {h.client.id for h in rows}

    # ---- aggregates over the filtered set
    health_counts = {
        c: sum(1 for h in rows if h.health.colour == c) for c in ("red", "amber", "green")
    }
    stage_counts = [(s, sum(1 for h in rows if h.client.current_stage_id == s.id)) for s in stages]

    # time in stage: completed visits only (an open visit has no duration yet)
    visits: dict[int, list[float]] = {s.id: [] for s in stages}
    for h in rows:
        for v in h.client.stage_history:
            if v.exited_at is not None:
                visits[v.stage_id].append((v.exited_at - v.entered_at).total_seconds() / 86400)
    stage_averages = [
        {
            "stage": s,
            "completed_visits": len(visits[s.id]),
            "avg_days": round(sum(visits[s.id]) / len(visits[s.id]), 1) if visits[s.id] else None,
            "max_days": round(max(visits[s.id]), 1) if visits[s.id] else None,
            "limit": cfg.stage_max_days.get(s.key),
        }
        for s in stages
    ]
    completed_visits = sum(len(v) for v in visits.values())

    overdue = [m for m in q.overdue_milestones(db, now.date()) if m.client_id in ids][:10]
    oldest_blockers = [
        b
        for b in db.scalars(
            select(Blocker)
            .options(selectinload(Blocker.client), selectinload(Blocker.owner))
            .where(Blocker.resolved_at.is_(None))
            .order_by(Blocker.opened_at)
        )
        if b.client_id in ids
    ][:10]

    chart_data = {
        "stages": {
            "labels": [_short(s.name) for s, _ in stage_counts],
            "values": [n for _, n in stage_counts],
        },
        "health": health_counts,
        "duration": {
            "labels": [_short(a["stage"].name) for a in stage_averages],
            "avg": [a["avg_days"] for a in stage_averages],
            "threshold": [a["limit"] for a in stage_averages],
        },
    }

    return templates.TemplateResponse(
        request,
        "insights.html",
        {
            "now": now,
            "chart_data": chart_data,
            "filters": {
                "owner_id": owner_id,
                "segment": segment,
                "stage": stage,
                "kickoff_from": kickoff_from,
                "kickoff_to": kickoff_to,
            },
            "filtered": bool(owner_id or segment or stage or kickoff_from or kickoff_to),
            "users": list(db.scalars(select(User).where(User.is_active).order_by(User.name))),
            "segments": CLIENT_SEGMENTS,
            "stages": stages,
            "n_accounts": len(rows),
            "completed_visits": completed_visits,
            "health_counts": health_counts,
            "stage_counts": stage_counts,
            "stage_averages": stage_averages,
            "overdue": overdue,
            "oldest_blockers": oldest_blockers,
        },
    )
