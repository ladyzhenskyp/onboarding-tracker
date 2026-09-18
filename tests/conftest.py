"""Test fixtures: a throwaway SQLite database, seeded once per test session.

DATABASE_URL is set *before* the app is imported, because app.config reads it
at import time. That's why the imports below sit under the environment line.
"""

import os
import tempfile
from pathlib import Path

import pytest

_TMP = Path(tempfile.mkdtemp(prefix="tracker-test-"))
os.environ["DATABASE_URL"] = f"sqlite:///{_TMP / 'test.db'}"
os.environ.setdefault("DEMO_USERNAME", "demo")
os.environ.setdefault("DEMO_PASSWORD", "demo1234")
os.environ.setdefault("SECRET_KEY", "test-secret")

from fastapi.testclient import TestClient  # noqa: E402

from app.database import engine  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Base, Stage  # noqa: E402
from app.models.stage import PIPELINE_STAGES  # noqa: E402
from scripts.seed import run as seed_run  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def seeded_database():
    Base.metadata.create_all(engine)
    from app.database import SessionLocal

    with SessionLocal() as db:
        if not db.query(Stage).count():
            db.add_all([Stage(key=k, name=n, sort_order=o) for k, n, o in PIPELINE_STAGES])
            db.commit()
    seed_run()
    yield


@pytest.fixture()
def client():
    """A signed-in test client (the demo login guards every page)."""
    c = TestClient(app)
    c.post("/login", data={"username": "demo", "password": "demo1234"})
    return c


@pytest.fixture()
def anon():
    """A test client with no session cookie."""
    return TestClient(app)
