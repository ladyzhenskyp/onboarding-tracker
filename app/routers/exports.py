"""CSV exports — Excel-friendly (UTF-8 with BOM, CRLF line endings)."""

from __future__ import annotations

import csv
import io
from datetime import datetime

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.deps import get_db, get_now, get_risk_config
from app.models import Blocker
from app.services import queries as q
from app.services.risk import RiskConfig

router = APIRouter(prefix="/export", tags=["export"])


def _csv_response(filename: str, header: list[str], rows: list[list]) -> StreamingResponse:
    buf = io.StringIO()
    buf.write("﻿")  # BOM so Excel opens UTF-8 correctly
    writer = csv.writer(buf, lineterminator="\r\n")
    writer.writerow(header)
    writer.writerows(rows)
    buf.seek(0)
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/pipeline.csv", name="export_pipeline")
def export_pipeline(
    db: Session = Depends(get_db),
    now: datetime = Depends(get_now),
    cfg: RiskConfig = Depends(get_risk_config),
):
    rows = []
    for h in q.client_health(db, now, cfg):
        c = h.client
        rows.append(
            [
                c.id,
                c.name,
                c.segment,
                f"{c.contract_value:.2f}",
                c.owner.name,
                c.current_stage.name,
                h.days_in_stage,
                c.kickoff_date.isoformat(),
                c.target_go_live_date.isoformat(),
                h.days_to_go_live,
                h.health.colour,
                "; ".join(r.message for r in h.health.reasons),
            ]
        )
    header = [
        "id",
        "client",
        "segment",
        "contract_value",
        "owner",
        "stage",
        "days_in_stage",
        "kickoff_date",
        "target_go_live",
        "days_to_go_live",
        "health",
        "reasons",
    ]
    return _csv_response(f"pipeline_{now:%Y-%m-%d}.csv", header, rows)


@router.get("/blockers.csv", name="export_blockers")
def export_blockers(db: Session = Depends(get_db), now: datetime = Depends(get_now)):
    stmt = (
        select(Blocker)
        .options(selectinload(Blocker.client), selectinload(Blocker.owner))
        .order_by(Blocker.resolved_at.is_not(None), Blocker.opened_at)
    )
    rows = []
    for b in db.scalars(stmt):
        rows.append(
            [
                b.id,
                b.client.name,
                b.title,
                b.severity,
                b.owner.name if b.owner else "",
                b.external_ref or "",
                b.opened_at.date().isoformat(),
                b.resolved_at.date().isoformat() if b.resolved_at else "",
                "open" if b.is_open else "closed",
                b.age_days(now),
            ]
        )
    header = [
        "id",
        "client",
        "title",
        "severity",
        "owner",
        "external_ref",
        "opened",
        "resolved",
        "status",
        "age_days",
    ]
    return _csv_response(f"blockers_{now:%Y-%m-%d}.csv", header, rows)
