"""The nightly demo reset: scheduling maths, and that a reset really restores the story."""

from datetime import datetime, timezone

from sqlalchemy import func, select

from app.database import SessionLocal
from app.models import Client, Note
from app.services import demo_reset


def test_seconds_until_next_run():
    at = lambda h, m=0: datetime(2026, 9, 20, h, m, tzinfo=timezone.utc)  # noqa: E731
    assert demo_reset.seconds_until(8, at(7)) == 3600  # later today
    assert demo_reset.seconds_until(8, at(9)) == 23 * 3600  # already passed -> tomorrow
    assert demo_reset.seconds_until(8, at(8)) == 24 * 3600  # exactly now -> tomorrow, never 0
    assert demo_reset.seconds_until_next_hour(at(7, 45)) == 15 * 60
    assert demo_reset.seconds_until_next_hour(at(7)) == 3600  # on the hour -> next hour, never 0


def test_reset_undoes_visitor_changes_and_keeps_ids(client):
    client.post("/clients/1/notes", data={"body": "visitor scribble"})
    client.post("/clients/1/stage/advance")
    with SessionLocal() as db:
        before = db.get(Client, 1).name
        assert db.scalar(
            select(func.count()).select_from(Note).where(Note.body == "visitor scribble")
        )

    demo_reset.reseed()

    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(Client)) == 20
        assert db.get(Client, 1).name == before  # same account behind /clients/1
        assert not db.scalar(
            select(func.count()).select_from(Note).where(Note.body == "visitor scribble")
        )
    r = client.get("/")
    assert "Ledgerline Capital" in r.text  # the designed red account is back on the dashboard


def test_reset_retries_after_a_failure(monkeypatch):
    import asyncio

    calls = []

    def flaky():
        calls.append(1)
        if len(calls) < 3:
            raise RuntimeError("deadlock detected")

    monkeypatch.setattr(demo_reset, "reseed", flaky)
    assert asyncio.run(demo_reset.reseed_with_retry(wait=0)) is True
    assert len(calls) == 3  # failed twice, succeeded on the third try

    calls.clear()
    monkeypatch.setattr(demo_reset, "reseed", lambda: (_ for _ in ()).throw(RuntimeError("no")))
    assert asyncio.run(demo_reset.reseed_with_retry(wait=0)) is False  # gives up quietly


def test_missing_page_is_friendly_for_people_and_plain_for_htmx(client):
    page = client.get("/clients/9999", headers={"accept": "text/html"})
    assert page.status_code == 404 and "isn't here any more" in page.text and "<html" in page.text
    hx = client.post("/clients/3/notes/999999/delete", headers={"HX-Request": "true"})
    assert hx.status_code == 404 and "<html" not in hx.text


def test_countdown_note_only_when_resets_are_on(client, monkeypatch):
    import dataclasses

    from app.config import settings

    assert "reset-note" not in client.get("/").text  # resets are off in tests and local dev
    on = dataclasses.replace(settings, demo_reset_nightly=True)
    monkeypatch.setattr(demo_reset, "settings", on)
    assert 'id="reset-note"' in client.get("/").text
