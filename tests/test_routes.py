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
    assert "badge red" in page and "Prod cert expired" in page
    with SessionLocal() as db:
        bid = db.scalar(select(Blocker.id).where(Blocker.title == "Prod cert expired"))
    client.post(f"/clients/{cid}/blockers/{bid}/resolve")
    assert "badge green" in client.get(f"/clients/{cid}").text


def test_add_milestone_and_note(client):
    cid = _client_id("Pinewood Family Office")
    client.post(
        f"/clients/{cid}/milestones", data={"title": "Signed SOW", "due_date": "2030-01-01"}
    )
    client.post(f"/clients/{cid}/notes", data={"body": "Note from the test suite"})
    page = client.get(f"/clients/{cid}").text
    assert "Signed SOW" in page and "Note from the test suite" in page
