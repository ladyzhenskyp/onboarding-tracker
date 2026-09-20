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
