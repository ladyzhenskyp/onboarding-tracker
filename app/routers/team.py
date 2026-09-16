from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.deps import get_db, get_now, get_risk_config, templates
from app.services import queries as q
from app.services.risk import RiskConfig

router = APIRouter(tags=["team"])


@router.get("/team", name="team")
def team(
    request: Request,
    db: Session = Depends(get_db),
    now: datetime = Depends(get_now),
    cfg: RiskConfig = Depends(get_risk_config),
):
    health = q.client_health(db, now, cfg)
    by_owner: dict[int, dict] = {}
    for h in health:
        d = by_owner.setdefault(
            h.client.owner_id, {"red": 0, "amber": 0, "green": 0, "clients": []}
        )
        d[h.health.colour] += 1
        d["clients"].append(h)
    rows = []
    for w in q.owner_workload(db):
        extra = by_owner.get(w.owner.id, {"red": 0, "amber": 0, "green": 0, "clients": []})
        rows.append({"w": w, **extra})
    return templates.TemplateResponse(request, "team.html", {"now": now, "rows": rows})
