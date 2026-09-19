from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.deps import get_db, get_now, get_risk_config, templates
from app.services import queries as q
from app.services.risk import RiskConfig
from app.services.stages import ordered_stages

router = APIRouter(tags=["pipeline"])


@router.get("/pipeline", name="pipeline")
def pipeline(
    request: Request,
    db: Session = Depends(get_db),
    now: datetime = Depends(get_now),
    cfg: RiskConfig = Depends(get_risk_config),
):
    health = q.client_health(db, now, cfg)
    columns = []
    for stage in ordered_stages(db):
        cards = sorted(
            (h for h in health if h.client.current_stage_id == stage.id),
            key=lambda h: (-{"red": 2, "amber": 1, "green": 0}[h.health.colour], -h.days_in_stage),
        )
        columns.append({"stage": stage, "cards": cards})
    return templates.TemplateResponse(
        request, "pipeline.html", {"now": now, "cfg": cfg, "columns": columns}
    )
