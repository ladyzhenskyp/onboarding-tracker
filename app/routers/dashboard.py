from __future__ import annotations

from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.deps import get_db, get_now, get_risk_config, templates
from app.models import Blocker
from app.services import queries as q
from app.services.risk import RiskConfig

router = APIRouter(tags=["dashboard"])

# The dashboard is a triage screen: what needs a human today. Charts and
# aggregate tables live on /insights so this page stays short.
THIS_WEEK_DAYS = 14
STRIP_LIMIT = 3


@router.get("/", name="dashboard")
def dashboard(
    request: Request,
    db: Session = Depends(get_db),
    now: datetime = Depends(get_now),
    cfg: RiskConfig = Depends(get_risk_config),
):
    health = q.client_health(db, now, cfg)
    at_risk = sorted(
        (h for h in health if h.health.is_at_risk),
        key=lambda h: ({"red": 0, "amber": 1}[h.health.colour], h.days_to_go_live),
    )
    health_counts = {
        c: sum(1 for h in health if h.health.colour == c) for c in ("red", "amber", "green")
    }

    horizon = now.date() + timedelta(days=THIS_WEEK_DAYS)
    upcoming = sorted(
        (
            h
            for h in health
            if h.client.current_stage.key != "live" and h.client.target_go_live_date <= horizon
        ),
        key=lambda h: h.client.target_go_live_date,
    )[:STRIP_LIMIT]

    oldest_blockers = list(
        db.scalars(
            select(Blocker)
            .options(selectinload(Blocker.client), selectinload(Blocker.owner))
            .where(Blocker.resolved_at.is_(None))
            .order_by(Blocker.opened_at)
            .limit(STRIP_LIMIT)
        )
    )

    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {
            "now": now,
            "cfg": cfg,
            "total_clients": len(health),
            "health_counts": health_counts,
            "at_risk": at_risk,
            "upcoming": upcoming,
            "oldest_blockers": oldest_blockers,
        },
    )
