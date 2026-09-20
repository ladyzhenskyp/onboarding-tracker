"""Route tests against the seeded demo database (see conftest.py)."""

import csv
import io

from sqlalchemy import select

from app.database import SessionLocal
from app.models import Blocker, Client, ClientStageHistory


def _client_id(name: str) -> int:
    with SessionLocal() as db:
        return db.scalar(select(Client.id).where(Client.name == name))


# ---- pages -------------------------------------------------------------------
def test_healthz(client):
    assert client.get("/healthz").json() == {"status": "ok"}


def test_dashboard_lists_at_risk_accounts_with_reasons(client):
    r = client.get("/")
    assert r.status_code == 200
    assert "At-risk accounts" in r.text
    assert "Ledgerline Capital" in r.text  # critical blocker -> red
    assert "Open critical blocker" in r.text
    assert "Acme Brokerage" not in r.text.split("At-risk accounts")[1].split("Go-lives")[0]


def test_pipeline_has_five_columns(client):
    r = client.get("/pipeline")
    assert r.status_code == 200
    for name in ("Kickoff", "Discovery / Configuration", "UAT", "Prod", "Live"):
        assert name in r.text


def test_client_list_and_detail(client):
    assert client.get("/clients").status_code == 200
    cid = _client_id("Harborview Asset Mgmt")
    r = client.get(f"/clients/{cid}")
    assert r.status_code == 200
    assert "Why red" in r.text
    assert "Advance to Prod" in r.text


def test_unknown_client_is_404(client):
    assert client.get("/clients/99999").status_code == 404


def test_blockers_filters(client):
    assert client.get("/blockers").status_code == 200
    r = client.get("/blockers?status=all&severity=critical")
    assert r.status_code == 200
    assert "Production SSO metadata" in r.text
    assert client.get("/blockers?status=bogus").status_code == 422


def test_team_page(client):
    r = client.get("/team")
    assert r.status_code == 200
    assert "Tom Whitfield" in r.text


# ---- exports -----------------------------------------------------------------
def test_pipeline_csv_is_excel_friendly(client):
    r = client.get("/export/pipeline.csv")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/csv")
    assert r.text.startswith("﻿")  # BOM
    rows = list(csv.reader(io.StringIO(r.text.lstrip("﻿"))))
    assert rows[0][:3] == ["id", "client", "segment"]
    assert len(rows) == 1 + 20
    assert {row[10] for row in rows[1:]} == {"red", "amber", "green"}


def test_blockers_csv(client):
    r = client.get("/export/blockers.csv")
    rows = list(csv.reader(io.StringIO(r.text.lstrip("﻿"))))
    assert rows[0][0] == "id"
    assert len(rows) > 1


# ---- actions -----------------------------------------------------------------
def test_advance_stage_keeps_history_consistent(client):
    cid = _client_id("Acme Brokerage")  # starts in kickoff
    r = client.post(f"/clients/{cid}/stage/advance", follow_redirects=False)
    assert r.status_code == 303
    with SessionLocal() as db:
        c = db.get(Client, cid)
        assert c.current_stage.key == "discovery"
        open_rows = db.scalars(
            select(ClientStageHistory).where(
                ClientStageHistory.client_id == cid, ClientStageHistory.exited_at.is_(None)
            )
        ).all()
        assert len(open_rows) == 1 and open_rows[0].stage_id == c.current_stage_id
        assert any("Stage changed" in n.body for n in c.notes)


def test_advancing_a_live_client_flashes_a_message(client):
    cid = _client_id("Silverline Securities")
    r = client.post(f"/clients/{cid}/stage/advance", follow_redirects=False)
    assert r.status_code == 303
    assert "already" in r.headers["location"]


def test_add_and_resolve_blocker_changes_health(client):
    cid = _client_id("Kestrel Clearing")  # green
    client.post(
        f"/clients/{cid}/blockers",
        data={"title": "Prod cert expired", "severity": "critical", "external_ref": "IMPL-777"},
    )
    page = client.get(f"/clients/{cid}").text
    assert "badge-red" in page and "Prod cert expired" in page
    with SessionLocal() as db:
        bid = db.scalar(select(Blocker.id).where(Blocker.title == "Prod cert expired"))
    client.post(f"/clients/{cid}/blockers/{bid}/resolve")
    assert "badge-green" in client.get(f"/clients/{cid}").text


def test_add_milestone_and_note(client):
    cid = _client_id("Pinewood Family Office")
    client.post(
        f"/clients/{cid}/milestones", data={"title": "Signed SOW", "due_date": "2030-01-01"}
    )
    client.post(f"/clients/{cid}/notes", data={"body": "Note from the test suite"})
    page = client.get(f"/clients/{cid}").text
    assert "Signed SOW" in page and "Note from the test suite" in page


# ---- HTMX --------------------------------------------------------------------
HX = {"HX-Request": "true"}


def test_htmx_action_returns_fragment_not_redirect(client):
    cid = _client_id("Granite Peak Partners")
    r = client.post(f"/clients/{cid}/notes", data={"body": "HTMX note"}, headers=HX)
    assert r.status_code == 200  # fragment, not a 303
    assert r.text.lstrip().startswith('<div id="client-body">')
    assert "<html" not in r.text  # only the swappable block, not the whole page
    assert "HTMX note" in r.text


def test_htmx_stage_error_is_flashed_in_fragment(client):
    cid = _client_id("Vantage Point Research")  # live
    r = client.post(f"/clients/{cid}/stage/advance", headers=HX)
    assert r.status_code == 200
    assert "already Live" in r.text


def test_insights_embeds_chart_data(client):
    r = client.get("/insights")
    assert '"stages"' in r.text and '"threshold"' in r.text
    assert "chart-duration" in r.text


# ---- auth --------------------------------------------------------------------
def test_anonymous_is_redirected_to_login(anon):
    r = anon.get("/", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"].startswith("/login")
    assert anon.get("/healthz").status_code == 200  # health check stays public


def test_anonymous_htmx_gets_hx_redirect(anon):
    r = anon.post("/clients/1/notes", data={"body": "x"}, headers=HX)
    assert r.status_code == 401 and r.headers["HX-Redirect"] == "/login"


def test_login_wrong_password_shows_error(anon):
    r = anon.post("/login", data={"username": "demo", "password": "nope"})
    assert r.status_code == 401 and "t match." in r.text


def test_login_then_logout(anon):
    r = anon.post(
        "/login",
        data={"username": "demo", "password": "demo1234", "next": "/team"},
        follow_redirects=False,
    )
    assert r.status_code == 303 and r.headers["location"] == "/team"
    assert anon.get("/team").status_code == 200
    anon.post("/logout")
    assert anon.get("/team", follow_redirects=False).status_code == 303


# ---- insights & search ---------------------------------------------------------
def test_insights_page_and_filters(client):
    r = client.get("/insights")
    assert r.status_code == 200
    assert "completed stage visit" in r.text
    assert "chart-duration" in r.text
    r = client.get("/insights?segment=enterprise&stage=uat")
    assert r.status_code == 200
    r = client.get("/insights?kickoff_from=2099-01-01")
    assert r.status_code == 200
    assert "No accounts match" in r.text
    assert client.get("/insights?kickoff_from=not-a-date").status_code == 422


def test_dashboard_has_no_charts_but_links_to_insights(client):
    r = client.get("/")
    assert "chart.umd.js" not in r.text
    assert 'href="/insights"' in r.text
    assert "This week" in r.text


def test_search_matches_clients_and_ticket_refs(client):
    r = client.get("/search?q=ledger")
    assert r.status_code == 200
    assert "Ledgerline Capital" in r.text
    with SessionLocal() as db:
        ref = db.scalar(select(Blocker.external_ref).where(Blocker.external_ref.is_not(None)))
    r = client.get(f"/search?q={ref}")
    assert ref in r.text
    assert "Type a client name" in client.get("/search?q=").text  # empty query -> hint
    assert "Nothing matches" in client.get("/search?q=zzzzqq").text


def test_client_peek_is_a_fragment_with_link_to_full_page(client):
    r = client.get("/clients/1/peek")
    assert r.status_code == 200
    assert "<html" not in r.text  # a fragment for the side panel, not a page
    assert "Open full page" in r.text and 'href="/clients/1"' in r.text
    assert client.get("/clients/9999/peek").status_code == 404


def test_filters_accept_the_blank_fields_a_browser_form_sends(client):
    # an untouched <select> or date field is submitted as "", which must mean "no filter"
    r = client.get("/insights?owner_id=2&segment=&stage=&kickoff_from=&kickoff_to=")
    assert r.status_code == 200 and "completed stage visit" in r.text
    assert client.get("/insights?owner_id=abc").status_code == 422  # present but malformed
    r = client.get("/blockers?status=open&severity=&owner_id=&client_id=")
    assert r.status_code == 200


def test_add_forms_accept_blank_optional_dropdowns(client):
    """A browser submits an untouched "Owner (optional)" dropdown as "", not as missing."""
    hx = {"HX-Request": "true"}
    r = client.post("/clients/3/notes", data={"body": "blank author", "author_id": ""}, headers=hx)
    assert r.status_code == 200 and "blank author" in r.text
    r = client.post(
        "/clients/3/milestones",
        data={"title": "Blank owner milestone", "due_date": "2030-01-15", "owner_id": ""},
        headers=hx,
    )
    assert r.status_code == 200 and "Blank owner milestone" in r.text
    r = client.post(
        "/clients/3/blockers",
        data={
            "title": "Blank owner blocker",
            "severity": "medium",
            "description": "",
            "external_ref": "",
            "owner_id": "",
        },
        headers=hx,
    )
    assert r.status_code == 200 and "Blank owner blocker" in r.text
    # and a chosen owner still works
    r = client.post("/clients/3/notes", data={"body": "with author", "author_id": "2"}, headers=hx)
    assert r.status_code == 200 and "with author" in r.text


# ---- edit / delete -------------------------------------------------------------------
HX = {"HX-Request": "true"}


def _ids(model, client_id):
    with SessionLocal() as db:
        return list(db.scalars(select(model.id).where(model.client_id == client_id)))


def test_edit_and_delete_milestone(client):
    from app.models import Milestone

    client.post(
        "/clients/3/milestones", data={"title": "Draft", "due_date": "2030-02-01", "owner_id": ""}
    )
    with SessionLocal() as db:
        mid = db.scalar(select(Milestone.id).where(Milestone.title == "Draft"))
    r = client.post(
        f"/clients/3/milestones/{mid}/edit",
        data={"title": "Final", "due_date": "2030-03-01", "status": "done", "owner_id": "2"},
        headers=HX,
    )
    assert r.status_code == 200 and "Final" in r.text
    with SessionLocal() as db:
        m = db.get(Milestone, mid)
        assert (m.title, m.status, m.owner_id) == ("Final", "done", 2) and m.completed_at
    # re-opening clears completed_at (the table requires the two to agree)
    client.post(
        f"/clients/3/milestones/{mid}/edit",
        data={"title": "Final", "due_date": "2030-03-01", "status": "in_progress", "owner_id": ""},
    )
    with SessionLocal() as db:
        m = db.get(Milestone, mid)
        assert m.status == "in_progress" and m.completed_at is None and m.owner_id is None
    assert client.post(f"/clients/3/milestones/{mid}/delete", headers=HX).status_code == 200
    assert mid not in _ids(Milestone, 3)


def test_edit_and_delete_blocker_changes_health(client):
    client.post(
        "/clients/3/blockers",
        data={"title": "Minor thing", "severity": "low", "owner_id": ""},
    )
    with SessionLocal() as db:
        bid = db.scalar(select(Blocker.id).where(Blocker.title == "Minor thing"))
    r = client.post(
        f"/clients/3/blockers/{bid}/edit",
        data={
            "title": "Major thing",
            "severity": "critical",
            "external_ref": "IMPL-999",
            "description": "now serious",
            "owner_id": "",
        },
        headers=HX,
    )
    assert r.status_code == 200 and "IMPL-999" in r.text
    assert "Why red" in r.text  # a critical blocker turns the account red straight away
    assert client.post(f"/clients/3/blockers/{bid}/delete", headers=HX).status_code == 200
    assert bid not in _ids(Blocker, 3)


def test_edit_and_delete_note_but_not_stage_history(client):
    from app.models import Note

    client.post("/clients/3/notes", data={"body": "typo heer", "author_id": ""})
    with SessionLocal() as db:
        nid = db.scalar(select(Note.id).where(Note.body == "typo heer"))
    r = client.post(
        f"/clients/3/notes/{nid}/edit", data={"body": "typo fixed", "author_id": "1"}, headers=HX
    )
    assert r.status_code == 200 and "typo fixed" in r.text and "typo heer" not in r.text
    assert client.post(f"/clients/3/notes/{nid}/delete", headers=HX).status_code == 200
    assert nid not in _ids(Note, 3)

    # stage moves are the audit trail: visible, but not editable or deletable
    client.post("/clients/3/stage/advance")
    with SessionLocal() as db:
        sys_id = db.scalar(
            select(Note.id).where(Note.client_id == 3, Note.body.like("Stage changed%"))
        )
    assert client.post(f"/clients/3/notes/{sys_id}/delete").status_code == 403
    assert client.post(f"/clients/3/notes/{sys_id}/edit", data={"body": "x"}).status_code == 403


def test_cannot_touch_another_clients_rows(client):
    from app.models import Note

    other = _ids(Note, 4)[0]
    assert client.post(f"/clients/3/notes/{other}/delete").status_code == 404
    assert other in _ids(Note, 4)


# ---- milestones order, meetings, add client, calendar -----------------------------------
def test_overdue_milestones_are_listed_first(client):
    client.post("/clients/3/milestones", data={"title": "AAA far future", "due_date": "2035-01-01"})
    client.post(
        "/clients/3/milestones", data={"title": "ZZZ long overdue", "due_date": "2020-01-01"}
    )
    body = client.get("/clients/3").text
    rows = body.split("Milestones")[1]
    assert rows.index("ZZZ long overdue") < rows.index("AAA far future")
    first_row = rows.split("<tr", 2)[2]  # [0] before thead row, [1] header, [2] first data row
    assert "ZZZ long overdue" in first_row and "Overdue" in first_row


def test_add_edit_delete_meeting_and_calendar(client):
    from app.models import Meeting

    r = client.post(
        "/clients/3/meetings",
        data={
            "summary": "Kickoff prep call",
            "held_on": "2031-05-14",
            "held_time": "14:30",
            "attendee_ids": ["1", "2"],
            "action_items": "",
        },
        headers=HX,
    )
    assert r.status_code == 200 and "Kickoff prep call" in r.text and "upcoming" in r.text
    with SessionLocal() as db:
        m = db.scalar(select(Meeting).where(Meeting.summary == "Kickoff prep call"))
        mid = m.id
        assert m.held_at.hour == 14 and sorted(u.id for u in m.attendees) == [1, 2]

    cal = client.get("/calendar?month=2031-05")
    assert cal.status_code == 200 and "May 2031" in cal.text and "2:30 pm" in cal.text
    assert "2:30 pm" not in client.get("/calendar?month=2031-05&person_id=5").text  # not attending
    assert "2:30 pm" in client.get("/calendar?month=2031-05&person_id=2").text
    assert client.get("/calendar?month=nonsense&person_id=").status_code == 200  # falls back

    r = client.post(
        f"/clients/3/meetings/{mid}/edit",
        data={
            "summary": "Kickoff prep (moved)",
            "held_on": "2031-05-15",
            "held_time": "09:00",
            "attendee_ids": ["3"],
        },
        headers=HX,
    )
    assert r.status_code == 200 and "Kickoff prep (moved)" in r.text
    assert client.post(f"/clients/3/meetings/{mid}/delete", headers=HX).status_code == 200
    assert mid not in _ids(Meeting, 3)


def test_seed_has_upcoming_meetings_for_the_calendar(client):
    r = client.get("/calendar")
    assert r.status_code == 200 and 'class="ev ' in r.text


def test_add_client_creates_history_and_validates(client):
    from app.models import Client, ClientStageHistory

    good = {
        "name": "  Northwind   Asset Mgmt ",
        "segment": "enterprise",
        "contract_value": "$120,000",
        "owner_id": "2",
        "kickoff_date": "2026-09-01",
        "target_go_live_date": "2026-12-01",
        "stage_key": "kickoff",
    }
    r = client.post("/clients", data=good, follow_redirects=False)
    assert r.status_code == 303
    with SessionLocal() as db:
        c = db.scalar(select(Client).where(Client.name == "Northwind Asset Mgmt"))
        assert c and c.contract_value == 120000 and c.current_stage.key == "kickoff"
        rows = list(
            db.scalars(select(ClientStageHistory).where(ClientStageHistory.client_id == c.id))
        )
        assert len(rows) == 1 and rows[0].exited_at is None  # one open history row
        cid = c.id
    page = client.get(f"/clients/{cid}")
    assert page.status_code == 200 and "Northwind Asset Mgmt" in page.text
    assert "Northwind Asset Mgmt" in client.get("/pipeline").text

    # problems come back as a message on the form, which stays filled in
    for change, message in [
        ({}, "already a client"),
        ({"name": "Other Co", "target_go_live_date": "2026-01-01"}, "before the kickoff"),
        ({"name": "Other Co", "contract_value": "lots"}, "should be a number"),
        ({"name": "Other Co", "owner_id": ""}, "Choose an owner"),
        ({"name": "Other Co", "segment": ""}, "Choose a segment"),
        ({"name": "Other Co", "kickoff_date": ""}, "kickoff date"),
    ]:
        r = client.post("/clients", data={**good, **change}, follow_redirects=False)
        assert r.status_code == 400 and message in r.text, message
    assert 'value="Other Co"' in r.text


def test_insights_blockers_table_sits_under_time_in_stage(client):
    t = client.get("/insights").text
    assert (
        t.index("Time in stage") < t.index("Oldest open blockers") < t.index("Overdue milestones")
    )
