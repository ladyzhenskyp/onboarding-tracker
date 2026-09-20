from __future__ import annotations

from datetime import date, datetime, time
from decimal import Decimal, InvalidOperation

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.deps import get_db, get_now, get_risk_config, opt_int, templates
from app.models import (
    BLOCKER_SEVERITIES,
    CLIENT_SEGMENTS,
    MILESTONE_STATUSES,
    Blocker,
    Client,
    Meeting,
    Milestone,
    Note,
    Stage,
    User,
)
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
            selectinload(Client.meetings).selectinload(Meeting.attendees),
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
    context = _detail_context(db, client_id, now, cfg, flash)
    template = "clients/_body.html" if _is_htmx(request) else "clients/detail.html"
    return templates.TemplateResponse(request, template, context)


def _detail_context(
    db: Session, client_id: int, now: datetime, cfg: RiskConfig, flash: str | None = None
) -> dict:
    """Everything the client templates need; shared by the full page and the peek panel."""
    client = _load_client(db, client_id)
    health = evaluate_client(client, now, cfg)
    open_row = next((h for h in client.stage_history if h.exited_at is None), None)
    days_in_stage = (now - (open_row.entered_at if open_row else client.created_at)).days
    stages = ordered_stages(db)
    context = {
        "now": now,
        "cfg": cfg,
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
        "milestone_statuses": MILESTONE_STATUSES,
        "milestones": _sorted_milestones(client, now.date()),
        "open_blockers": [b for b in client.blockers if b.is_open],
        "closed_blockers": [b for b in client.blockers if not b.is_open],
        "flash": flash,
    }
    return context


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
    return _render_list(request, db, now, cfg)


def _render_list(
    request: Request,
    db: Session,
    now: datetime,
    cfg: RiskConfig,
    form_error: str | None = None,
    form: dict | None = None,
    status_code: int = 200,
):
    context = {
        "now": now,
        "cfg": cfg,
        "rows": q.client_health(db, now, cfg),
        "users": list(db.scalars(select(User).where(User.is_active).order_by(User.name))),
        "segments": CLIENT_SEGMENTS,
        "stages": ordered_stages(db),
        "today": now.date(),
        "form_error": form_error,
        "form": form or {},
    }
    return templates.TemplateResponse(
        request, "clients/list.html", context, status_code=status_code
    )


@router.post("", name="client_create")
def client_create(
    request: Request,
    name: str = Form(""),
    segment: str = Form(""),
    contract_value: str = Form(""),
    owner_id: str = Form(""),
    kickoff_date: str = Form(""),
    target_go_live_date: str = Form(""),
    stage_key: str = Form("kickoff"),
    db: Session = Depends(get_db),
    now: datetime = Depends(get_now),
    cfg: RiskConfig = Depends(get_risk_config),
):
    """Add a client. On a problem the page comes back with the form still filled in and a
    plain-English message, rather than an error page."""
    form = {
        "name": name, "segment": segment, "contract_value": contract_value,
        "owner_id": owner_id, "kickoff_date": kickoff_date,
        "target_go_live_date": target_go_live_date, "stage_key": stage_key,
    }  # fmt: skip

    def problem(message: str):
        return _render_list(request, db, now, cfg, message, form, status_code=400)

    try:
        value = Decimal(contract_value.replace(",", "").replace("$", "").strip())
    except (InvalidOperation, AttributeError):
        return problem("Contract value should be a number, for example 120000.")
    try:
        kickoff = date.fromisoformat(kickoff_date)
        go_live = date.fromisoformat(target_go_live_date)
    except ValueError:
        return problem("Choose both a kickoff date and a target go-live date.")
    owner = _person(db, owner_id)
    stage = db.scalar(select(Stage).where(Stage.key == stage_key))
    if segment not in CLIENT_SEGMENTS:
        return problem("Choose a segment.")
    if owner is None:
        return problem("Choose an owner. Every account needs someone responsible for it.")
    if stage is None:
        return problem("Choose a stage.")
    try:
        client = actions.create_client(
            db, name=name, segment=segment, contract_value=value, owner=owner,
            kickoff_date=kickoff, target_go_live_date=go_live, stage=stage, now=now,
        )  # fmt: skip
    except actions.ClientError as e:
        return problem(str(e))
    return RedirectResponse(url=f"/clients/{client.id}", status_code=303)


@router.get("/{client_id}", name="client_detail")
def client_detail(
    client_id: int,
    request: Request,
    db: Session = Depends(get_db),
    now: datetime = Depends(get_now),
    cfg: RiskConfig = Depends(get_risk_config),
):
    return _render_detail(request, db, client_id, now, cfg, request.query_params.get("msg"))


@router.get("/{client_id}/peek", name="client_peek")
def client_peek(
    client_id: int,
    request: Request,
    db: Session = Depends(get_db),
    now: datetime = Depends(get_now),
    cfg: RiskConfig = Depends(get_risk_config),
):
    """Quick-look panel: a compact fragment that lists open from any table row.
    It reuses the full page's context, so the two can never disagree."""
    context = _detail_context(db, client_id, now, cfg)
    return templates.TemplateResponse(request, "clients/_peek.html", context)


def _sorted_milestones(client: Client, today: date) -> list[Milestone]:
    """Overdue first (oldest first), then what's still open by due date, then done."""

    def rank(m: Milestone) -> tuple[int, date]:
        if m.is_overdue(today):
            return (0, m.due_date)
        return (2, m.due_date) if m.status == "done" else (1, m.due_date)

    return sorted(client.milestones, key=rank)


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
    owner_id: str | None = Form(None),
    db: Session = Depends(get_db),
    cfg: RiskConfig = Depends(get_risk_config),
    now: datetime = Depends(get_now),
):
    client = _load_client(db, client_id)
    if severity not in BLOCKER_SEVERITIES:
        raise HTTPException(status_code=400, detail="Invalid severity")
    # an untouched "Owner (optional)" dropdown is submitted as "", which means nobody
    owner = db.get(User, opt_int(owner_id)) if opt_int(owner_id) else None
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
    owner_id: str | None = Form(None),
    db: Session = Depends(get_db),
    cfg: RiskConfig = Depends(get_risk_config),
    now: datetime = Depends(get_now),
):
    client = _load_client(db, client_id)
    # an untouched "Owner (optional)" dropdown is submitted as "", which means nobody
    owner = db.get(User, opt_int(owner_id)) if opt_int(owner_id) else None
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
    author_id: str | None = Form(None),
    db: Session = Depends(get_db),
    cfg: RiskConfig = Depends(get_risk_config),
    now: datetime = Depends(get_now),
):
    client = _load_client(db, client_id)
    author = db.get(User, opt_int(author_id)) if opt_int(author_id) else None
    if body.strip():
        actions.add_note(db, client, body=body, now=now, author=author)
    return _after_action(request, db, client_id, now, cfg)


# ---- edit / delete --------------------------------------------------------------------
def _owned(db: Session, model, item_id: int, client_id: int, label: str):
    """Fetch a row and make sure it belongs to this client (so /clients/1/notes/99/delete
    can never touch another client's note)."""
    item = db.get(model, item_id)
    if item is None or item.client_id != client_id:
        raise HTTPException(status_code=404, detail=f"{label} not found")
    return item


def _person(db: Session, raw: str | None) -> User | None:
    """An untouched "(optional)" dropdown is submitted as "", which means nobody."""
    uid = opt_int(raw)
    return db.get(User, uid) if uid else None


@router.post("/{client_id}/milestones/{milestone_id}/edit", name="client_edit_milestone")
def client_edit_milestone(
    client_id: int,
    milestone_id: int,
    request: Request,
    title: str = Form(...),
    due_date: date = Form(...),
    status: str = Form(...),
    owner_id: str | None = Form(None),
    db: Session = Depends(get_db),
    cfg: RiskConfig = Depends(get_risk_config),
    now: datetime = Depends(get_now),
):
    m = _owned(db, Milestone, milestone_id, client_id, "Milestone")
    if status not in MILESTONE_STATUSES or not title.strip():
        raise HTTPException(status_code=422, detail="Invalid milestone")
    actions.update_milestone(
        db, m, title=title, due_date=due_date, status=status, now=now, owner=_person(db, owner_id)
    )
    return _after_action(request, db, client_id, now, cfg)


@router.post("/{client_id}/milestones/{milestone_id}/delete", name="client_delete_milestone")
def client_delete_milestone(
    client_id: int,
    milestone_id: int,
    request: Request,
    db: Session = Depends(get_db),
    cfg: RiskConfig = Depends(get_risk_config),
    now: datetime = Depends(get_now),
):
    actions.delete_milestone(db, _owned(db, Milestone, milestone_id, client_id, "Milestone"))
    return _after_action(request, db, client_id, now, cfg)


@router.post("/{client_id}/blockers/{blocker_id}/edit", name="client_edit_blocker")
def client_edit_blocker(
    client_id: int,
    blocker_id: int,
    request: Request,
    title: str = Form(...),
    severity: str = Form(...),
    description: str = Form(""),
    external_ref: str = Form(""),
    owner_id: str | None = Form(None),
    db: Session = Depends(get_db),
    cfg: RiskConfig = Depends(get_risk_config),
    now: datetime = Depends(get_now),
):
    b = _owned(db, Blocker, blocker_id, client_id, "Blocker")
    if severity not in BLOCKER_SEVERITIES or not title.strip():
        raise HTTPException(status_code=422, detail="Invalid blocker")
    actions.update_blocker(
        db,
        b,
        title=title,
        severity=severity,
        description=description,
        owner=_person(db, owner_id),
        external_ref=external_ref,
    )
    return _after_action(request, db, client_id, now, cfg)


@router.post("/{client_id}/blockers/{blocker_id}/delete", name="client_delete_blocker")
def client_delete_blocker(
    client_id: int,
    blocker_id: int,
    request: Request,
    db: Session = Depends(get_db),
    cfg: RiskConfig = Depends(get_risk_config),
    now: datetime = Depends(get_now),
):
    actions.delete_blocker(db, _owned(db, Blocker, blocker_id, client_id, "Blocker"))
    return _after_action(request, db, client_id, now, cfg)


def _editable_note(db: Session, note_id: int, client_id: int) -> Note:
    note = _owned(db, Note, note_id, client_id, "Note")
    if note.is_system:  # stage moves are the audit trail
        raise HTTPException(status_code=403, detail="Stage history can't be changed")
    return note


@router.post("/{client_id}/notes/{note_id}/edit", name="client_edit_note")
def client_edit_note(
    client_id: int,
    note_id: int,
    request: Request,
    body: str = Form(...),
    author_id: str | None = Form(None),
    db: Session = Depends(get_db),
    cfg: RiskConfig = Depends(get_risk_config),
    now: datetime = Depends(get_now),
):
    note = _editable_note(db, note_id, client_id)
    if not body.strip():
        raise HTTPException(status_code=422, detail="A note can't be empty")
    actions.update_note(db, note, body=body, author=_person(db, author_id))
    return _after_action(request, db, client_id, now, cfg)


@router.post("/{client_id}/notes/{note_id}/delete", name="client_delete_note")
def client_delete_note(
    client_id: int,
    note_id: int,
    request: Request,
    db: Session = Depends(get_db),
    cfg: RiskConfig = Depends(get_risk_config),
    now: datetime = Depends(get_now),
):
    actions.delete_note(db, _editable_note(db, note_id, client_id))
    return _after_action(request, db, client_id, now, cfg)


# ---- meetings -------------------------------------------------------------------------
def _meeting_fields(db: Session, held_on: str, held_time: str, attendee_ids: list[str]):
    try:
        when = datetime.combine(
            date.fromisoformat(held_on), time.fromisoformat(held_time or "10:00")
        )
    except ValueError:
        raise HTTPException(status_code=422, detail="Choose a date and time") from None
    ids = [i for i in (opt_int(a) for a in attendee_ids) if i]
    people = list(db.scalars(select(User).where(User.id.in_(ids)))) if ids else []
    return when, people


@router.post("/{client_id}/meetings", name="client_add_meeting")
def client_add_meeting(
    client_id: int,
    request: Request,
    held_on: str = Form(...),
    held_time: str = Form("10:00"),
    summary: str = Form(...),
    action_items: str = Form(""),
    attendee_ids: list[str] = Form([]),
    db: Session = Depends(get_db),
    cfg: RiskConfig = Depends(get_risk_config),
    now: datetime = Depends(get_now),
):
    client = _load_client(db, client_id)
    when, people = _meeting_fields(db, held_on, held_time, attendee_ids)
    if not summary.strip():
        raise HTTPException(status_code=422, detail="Say what the meeting is about")
    actions.add_meeting(
        db, client, held_at=when, summary=summary, attendees=people, action_items=action_items
    )
    return _after_action(request, db, client_id, now, cfg)


@router.post("/{client_id}/meetings/{meeting_id}/edit", name="client_edit_meeting")
def client_edit_meeting(
    client_id: int,
    meeting_id: int,
    request: Request,
    held_on: str = Form(...),
    held_time: str = Form("10:00"),
    summary: str = Form(...),
    action_items: str = Form(""),
    attendee_ids: list[str] = Form([]),
    db: Session = Depends(get_db),
    cfg: RiskConfig = Depends(get_risk_config),
    now: datetime = Depends(get_now),
):
    meeting = _owned(db, Meeting, meeting_id, client_id, "Meeting")
    when, people = _meeting_fields(db, held_on, held_time, attendee_ids)
    if not summary.strip():
        raise HTTPException(status_code=422, detail="Say what the meeting is about")
    actions.update_meeting(
        db, meeting, held_at=when, summary=summary, attendees=people, action_items=action_items
    )
    return _after_action(request, db, client_id, now, cfg)


@router.post("/{client_id}/meetings/{meeting_id}/delete", name="client_delete_meeting")
def client_delete_meeting(
    client_id: int,
    meeting_id: int,
    request: Request,
    db: Session = Depends(get_db),
    cfg: RiskConfig = Depends(get_risk_config),
    now: datetime = Depends(get_now),
):
    actions.delete_meeting(db, _owned(db, Meeting, meeting_id, client_id, "Meeting"))
    return _after_action(request, db, client_id, now, cfg)
