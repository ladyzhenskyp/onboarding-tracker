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
    return TestClient(app)
