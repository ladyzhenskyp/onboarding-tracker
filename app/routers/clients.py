from __future__ import annotations

from datetime import date, datetime

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.deps import get_db, get_now, get_risk_config, templates
from app.models import BLOCKER_SEVERITIES, Blocker, Client, Milestone, Stage, User
from app.services import actions
from app.services import queries as q
from app.services.risk import RiskConfig, evaluate_client
from app.services.stages import (
    StageTransitionError,
    advance_stage,
    move_to_stage,
    next_stage,
    ordered_stages,
)

router = APIRouter(prefix="/clients", tags=["clients"])


def _load_client(db: Session, client_id: int) -> Client:
    client = db.scalar(
        select(Client)
        .options(
            selectinload(Client.owner),
            selectinload(Client.current_stage),
            selectinload(Client.stage_history),
            selectinload(Client.milestones).selectinload(Milestone.owner),
            selectinload(Client.blockers).selectinload(Blocker.owner),
            selectinload(Client.notes),
            selectinload(Client.meetings),
        )
        .where(Client.id == client_id)
    )
    if client is None:
        raise HTTPException(status_code=404, detail="Client not found")
    return client


def _is_htmx(request: Request) -> bool:
    return request.headers.get("HX-Request") == "true"


def _render_detail(
    request: Request,
    db: Session,
    client_id: int,
    now: datetime,
    cfg: RiskConfig,
    flash: str | None = None,
):
    """Render the client page. For HTMX requests only the swappable body fragment
    is returned, so an action updates the page in place without a full reload."""
    client = _load_client(db, client_id)
    health = evaluate_client(client, now, cfg)
    open_row = next((h for h in client.stage_history if h.exited_at is None), None)
    days_in_stage = (now - (open_row.entered_at if open_row else client.created_at)).days
    stages = ordered_stages(db)
    context = {
        "now": now,
        "today": now.date(),
        "client": client,
        "health": health,
        "days_in_stage": days_in_stage,
        "days_to_go_live": (client.target_go_live_date - now.date()).days,
        "stages": stages,
        "next_stage": next_stage(db, client.current_stage),
        "timeline": _timeline(client, stages, now),
        "users": list(db.scalars(select(User).where(User.is_active).order_by(User.name))),
        "severities": BLOCKER_SEVERITIES,
        "open_blockers": [b for b in client.blockers if b.is_open],
        "closed_blockers": [b for b in client.blockers if not b.is_open],
        "flash": flash,
    }
    template = "clients/_body.html" if _is_htmx(request) else "clients/detail.html"
    return templates.TemplateResponse(request, template, context)


def _after_action(
    request: Request,
    db: Session,
    client_id: int,
    now: datetime,
    cfg: RiskConfig,
    flash: str | None = None,
):
    """HTMX callers get the refreshed fragment; plain form posts get a redirect."""
    if _is_htmx(request):
        return _render_detail(request, db, client_id, now, cfg, flash)
    url = f"/clients/{client_id}" + (f"?msg={flash}" if flash else "")
    return RedirectResponse(url=url, status_code=303)


@router.get("", name="client_list")
def client_list(
    request: Request,
    db: Session = Depends(get_db),
    now: datetime = Depends(get_now),
    cfg: RiskConfig = Depends(get_risk_config),
):
    rows = q.client_health(db, now, cfg)
    return templates.TemplateResponse(request, "clients/list.html", {"now": now, "rows": rows})


@router.get("/{client_id}", name="client_detail")
def client_detail(
    client_id: int,
    request: Request,
    db: Session = Depends(get_db),
    now: datetime = Depends(get_now),
    cfg: RiskConfig = Depends(get_risk_config),
):
    return _render_detail(request, db, client_id, now, cfg, request.query_params.get("msg"))


def _timeline(client: Client, stages: list[Stage], now: datetime) -> list[dict]:
    """One entry per pipeline stage: visited / current / upcoming, with days spent."""
    by_stage: dict[int, list] = {}
    for h in client.stage_history:
        by_stage.setdefault(h.stage_id, []).append(h)
    out = []
    for s in stages:
        visits = by_stage.get(s.id, [])
        days = sum(((v.exited_at or now) - v.entered_at).days for v in visits)
        if s.id == client.current_stage_id:
            state = "current"
        elif visits:
            state = "done"
        else:
            state = "upcoming"
        out.append({"stage": s, "state": state, "days": days, "visits": visits})
    return out


# ---- actions: HTMX gets the refreshed fragment, plain forms get a redirect ----
@router.post("/{client_id}/stage/advance", name="client_advance_stage")
def client_advance_stage(
    client_id: int,
    request: Request,
    db: Session = Depends(get_db),
    cfg: RiskConfig = Depends(get_risk_config),
    now: datetime = Depends(get_now),
):
    client = _load_client(db, client_id)
    try:
        advance_stage(db, client, now)
    except StageTransitionError as e:
        return _after_action(request, db, client_id, now, cfg, flash=str(e))
    return _after_action(request, db, client_id, now, cfg)


@router.post("/{client_id}/stage", name="client_move_stage")
def client_move_stage(
    client_id: int,
    request: Request,
    stage_key: str = Form(...),
    reason: str = Form(""),
    db: Session = Depends(get_db),
    cfg: RiskConfig = Depends(get_risk_config),
    now: datetime = Depends(get_now),
):
    client = _load_client(db, client_id)
    stage = db.scalar(select(Stage).where(Stage.key == stage_key))
    if stage is None:
        raise HTTPException(status_code=400, detail="Unknown stage")
    try:
        move_to_stage(db, client, stage, now, reason=reason or None)
    except StageTransitionError as e:
        return _after_action(request, db, client_id, now, cfg, flash=str(e))
    return _after_action(request, db, client_id, now, cfg)


@router.post("/{client_id}/blockers", name="client_add_blocker")
def client_add_blocker(
    client_id: int,
    request: Request,
    title: str = Form(...),
    severity: str = Form(...),
    description: str = Form(""),
    external_ref: str = Form(""),
    owner_id: int | None = Form(None),
    db: Session = Depends(get_db),
    cfg: RiskConfig = Depends(get_risk_config),
    now: datetime = Depends(get_now),
):
    client = _load_client(db, client_id)
    if severity not in BLOCKER_SEVERITIES:
        raise HTTPException(status_code=400, detail="Invalid severity")
    owner = db.get(User, owner_id) if owner_id else None
    actions.add_blocker(
        db,
        client,
        title=title,
        severity=severity,
        now=now,
        description=description,
        owner=owner,
        external_ref=external_ref,
    )
    return _after_action(request, db, client_id, now, cfg)


@router.post("/{client_id}/blockers/{blocker_id}/resolve", name="client_resolve_blocker")
def client_resolve_blocker(
    client_id: int,
    request: Request,
    blocker_id: int,
    db: Session = Depends(get_db),
    cfg: RiskConfig = Depends(get_risk_config),
    now: datetime = Depends(get_now),
):
    blocker = db.get(Blocker, blocker_id)
    if blocker is None or blocker.client_id != client_id:
        raise HTTPException(status_code=404, detail="Blocker not found")
    actions.resolve_blocker(db, blocker, now)
    return _after_action(request, db, client_id, now, cfg)


@router.post("/{client_id}/milestones", name="client_add_milestone")
def client_add_milestone(
    client_id: int,
    request: Request,
    title: str = Form(...),
    due_date: date = Form(...),
    owner_id: int | None = Form(None),
    db: Session = Depends(get_db),
    cfg: RiskConfig = Depends(get_risk_config),
    now: datetime = Depends(get_now),
):
    client = _load_client(db, client_id)
    owner = db.get(User, owner_id) if owner_id else None
    actions.add_milestone(db, client, title=title, due_date=due_date, owner=owner)
    return _after_action(request, db, client_id, now, cfg)


@router.post("/{client_id}/milestones/{milestone_id}/complete", name="client_complete_milestone")
def client_complete_milestone(
    client_id: int,
    request: Request,
    milestone_id: int,
    db: Session = Depends(get_db),
    cfg: RiskConfig = Depends(get_risk_config),
    now: datetime = Depends(get_now),
):
    m = db.get(Milestone, milestone_id)
    if m is None or m.client_id != client_id:
        raise HTTPException(status_code=404, detail="Milestone not found")
    actions.complete_milestone(db, m, now)
    return _after_action(request, db, client_id, now, cfg)


@router.post("/{client_id}/notes", name="client_add_note")
def client_add_note(
    client_id: int,
    request: Request,
    body: str = Form(...),
    author_id: int | None = Form(None),
    db: Session = Depends(get_db),
    cfg: RiskConfig = Depends(get_risk_config),
    now: datetime = Depends(get_now),
):
    client = _load_client(db, client_id)
    author = db.get(User, author_id) if author_id else None
    if body.strip():
        actions.add_note(db, client, body=body, now=now, author=author)
    return _after_action(request, db, client_id, now, cfg)
