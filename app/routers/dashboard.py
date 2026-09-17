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


def _short(stage_name: str) -> str:
    """Axis-friendly stage label."""
    return stage_name.split(" / ")[0]


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

    horizon = now.date() + timedelta(days=30)
    upcoming = sorted(
        (
            h
            for h in health
            if h.client.current_stage.key != "live"
            and now.date() <= h.client.target_go_live_date <= horizon
        ),
        key=lambda h: h.client.target_go_live_date,
    )

    oldest_blockers = list(
        db.scalars(
            select(Blocker)
            .options(selectinload(Blocker.client), selectinload(Blocker.owner))
            .where(Blocker.resolved_at.is_(None))
            .order_by(Blocker.opened_at)
            .limit(8)
        )
    )

    stage_counts = q.current_stage_counts(db)
    stage_averages = q.average_time_in_stage(db)
    # Chart.js reads this as JSON; thresholds come from the same config the rules use.
    chart_data = {
        "stages": {
            "labels": [_short(s.name) for s, _ in stage_counts],
            "values": [n for _, n in stage_counts],
        },
        "health": health_counts,
        "duration": {
            "labels": [_short(a.stage) for a in stage_averages],
            "avg": [a.avg_days for a in stage_averages],
            "threshold": [
                cfg.stage_max_days.get(s.key)
                for s, _ in stage_counts
                if s.name in {a.stage for a in stage_averages}
            ],
        },
    }

    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {
            "chart_data": chart_data,
            "now": now,
            "total_clients": len(health),
            "stage_counts": stage_counts,
            "health_counts": health_counts,
            "at_risk": at_risk,
            "upcoming": upcoming,
            "overdue": q.overdue_milestones(db, now.date())[:10],
            "oldest_blockers": oldest_blockers,
            "stage_averages": stage_averages,
        },
    )
