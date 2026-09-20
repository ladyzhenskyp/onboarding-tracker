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
