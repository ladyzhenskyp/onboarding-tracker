"""Shared FastAPI dependencies: templates, database session, risk config, clock."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from functools import lru_cache
from pathlib import Path

from fastapi.templating import Jinja2Templates

from app.config import settings
from app.database import get_db  # re-exported so routers import one module
from app.models import utcnow
from app.services.risk import RiskConfig

TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


# ---- Jinja2 filters -----------------------------------------------------------
def money(value: Decimal | float | int | None) -> str:
    if value is None:
        return "—"
    return f"${Decimal(value):,.0f}"


def fmt_date(value: date | datetime | None) -> str:
    if value is None:
        return "—"
    return value.strftime("%b %-d, %Y")


def humanize(value: str | None) -> str:
    """'mid_market' -> 'Mid market', 'in_progress' -> 'In progress'."""
    return (value or "").replace("_", " ").capitalize()


templates.env.filters["money"] = money
templates.env.filters["date"] = fmt_date
templates.env.filters["humanize"] = humanize


# ---- dependencies ----------------------------------------------------------------
@lru_cache(maxsize=1)
def get_risk_config() -> RiskConfig:
    return RiskConfig.from_yaml(settings.risk_rules_path)


def get_now() -> datetime:
    """Injected so tests can freeze time."""
    return utcnow()


__all__ = ["get_db", "get_now", "get_risk_config", "templates"]
