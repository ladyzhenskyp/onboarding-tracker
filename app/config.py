"""Application settings, loaded once from environment variables / .env.

Keeping every knob here means the rest of the app never touches os.environ.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

# Repo root = one level above app/. Load .env from there if present.
ROOT_DIR = Path(__file__).resolve().parent.parent
load_dotenv(ROOT_DIR / ".env")


@dataclass(frozen=True)
class Settings:
    database_url: str
    secret_key: str
    demo_username: str
    demo_password: str
    risk_rules_path: Path
    demo_reset_nightly: bool
    demo_reset_hour_utc: int
    demo_reset_schedule: str


def _env(name: str, default: str) -> str:
    value = os.getenv(name)
    return value if value not in (None, "") else default


def get_settings() -> Settings:
    db_url = _env("DATABASE_URL", "sqlite:///./tracker.db")
    # Render/Heroku hand out "postgres://" URLs; SQLAlchemy 2 wants "postgresql+psycopg://".
    if db_url.startswith("postgres://"):
        db_url = db_url.replace("postgres://", "postgresql+psycopg://", 1)
    elif db_url.startswith("postgresql://"):
        db_url = db_url.replace("postgresql://", "postgresql+psycopg://", 1)

    return Settings(
        database_url=db_url,
        secret_key=_env("SECRET_KEY", "dev-only-secret"),
        demo_username=_env("DEMO_USERNAME", "demo"),
        demo_password=_env("DEMO_PASSWORD", "demo1234"),
        risk_rules_path=Path(_env("RISK_RULES_PATH", str(ROOT_DIR / "app" / "risk_rules.yaml"))),
        # Nightly wipe-and-reseed of the shared demo (app/services/demo_reset.py). Off unless
        # asked for; scripts/start.sh turns it on in the container. 8 UTC = 4am New York (EDT).
        demo_reset_nightly=_env("DEMO_RESET_NIGHTLY", "false").lower() == "true",
        demo_reset_hour_utc=int(_env("DEMO_RESET_HOUR_UTC", "8")) % 24,
        # "hourly" resets on the hour; "nightly" resets once a day at DEMO_RESET_HOUR_UTC.
        demo_reset_schedule=(
            "nightly" if _env("DEMO_RESET_SCHEDULE", "hourly").lower() == "nightly" else "hourly"
        ),
    )


settings = get_settings()
