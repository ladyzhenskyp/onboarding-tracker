"""ORM equivalents of the SQL in queries/. Dialect-neutral (SQLite + Postgres).

The at-risk list reuses the rule engine rather than re-implementing the rules
in SQL, so there is exactly one definition of "at risk" in the app.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session, selectinload

from app.models import Blocker, Client, ClientStageHistory, Milestone, Stage, User
from app.services.risk import HealthResult, RiskConfig, evaluate_client


# --------------------------------------------------------------------------- at-risk
@dataclass(frozen=True)
class ClientHealth:
    client: Client
    health: HealthResult
    days_in_stage: int
    days_to_go_live: int


def load_clients_for_risk(db: Session) -> list[Client]:
    """Clients with everything the rules need, loaded in a handful of queries."""
    stmt = (
        select(Client)
        .options(
            selectinload(Client.owner),
            selectinload(Client.current_stage),
            selectinload(Client.stage_history),
            selectinload(Client.blockers),
            selectinload(Client.milestones),
        )
        .order_by(Client.name)
    )
    return list(db.scalars(stmt).unique())


def client_health(db: Session, now: datetime, cfg: RiskConfig) -> list[ClientHealth]:
    out: list[ClientHealth] = []
    for c in load_clients_for_risk(db):
        open_row = next((h for h in c.stage_history if h.exited_at is None), None)
        entered = open_row.entered_at if open_row else c.created_at
        out.append(
            ClientHealth(
                client=c,
                health=evaluate_client(c, now, cfg),
                days_in_stage=(now - entered).days,
                days_to_go_live=(c.target_go_live_date - now.date()).days,
            )
        )
    return out


def at_risk_accounts(db: Session, now: datetime, cfg: RiskConfig) -> list[ClientHealth]:
    rank = {"red": 0, "amber": 1, "green": 2}
    rows = [r for r in client_health(db, now, cfg) if r.health.is_at_risk]
    return sorted(rows, key=lambda r: (rank[r.health.colour], r.days_to_go_live))


# --------------------------------------------------------------------------- time in stage
@dataclass(frozen=True)
class StageAverage:
    stage: str
    completed_visits: int
    avg_days: float
    max_days: float


def _duration_days_expr():
    """(exited_at - entered_at) in days, written per dialect via a CASE-free trick:
    julianday() on SQLite; epoch arithmetic on Postgres. Chosen at execution time."""
    return func.julianday(ClientStageHistory.exited_at) - func.julianday(
        ClientStageHistory.entered_at
    )


def average_time_in_stage(db: Session) -> list[StageAverage]:
    dialect = db.get_bind().dialect.name
    if dialect == "sqlite":
        days = _duration_days_expr()
    else:  # postgresql
        days = (
            func.extract("epoch", ClientStageHistory.exited_at - ClientStageHistory.entered_at)
            / 86400.0
        )
    stmt = (
        select(
            Stage.name,
            func.count().label("completed_visits"),
            func.avg(days).label("avg_days"),
            func.max(days).label("max_days"),
        )
        .join(ClientStageHistory, ClientStageHistory.stage_id == Stage.id)
        .where(ClientStageHistory.exited_at.is_not(None))
        .group_by(Stage.name, Stage.sort_order)
        .order_by(Stage.sort_order)
    )
    return [
        StageAverage(name, int(n), round(float(avg or 0), 1), round(float(mx or 0), 1))
        for name, n, avg, mx in db.execute(stmt)
    ]


def current_stage_counts(db: Session) -> list[tuple[Stage, int]]:
    """Clients per stage, including zero-count stages (LEFT JOIN from stages)."""
    stmt = (
        select(Stage, func.count(Client.id))
        .outerjoin(Client, Client.current_stage_id == Stage.id)
        .group_by(Stage.id)
        .order_by(Stage.sort_order)
    )
    return [(s, int(n)) for s, n in db.execute(stmt)]


# --------------------------------------------------------------------------- overdue milestones
def overdue_milestones(db: Session, today: date) -> list[Milestone]:
    stmt = (
        select(Milestone)
        .options(selectinload(Milestone.client), selectinload(Milestone.owner))
        .where(Milestone.status != "done", Milestone.due_date < today)
        .order_by(Milestone.due_date, Milestone.client_id)
    )
    return list(db.scalars(stmt))


# --------------------------------------------------------------------------- owner workload
@dataclass(frozen=True)
class OwnerWorkload:
    owner: User
    accounts: int
    onboarding: int
    accounts_with_severe_blocker: int
    contract_value: Decimal


def owner_workload(db: Session) -> list[OwnerWorkload]:
    severe = (
        select(Blocker.client_id)
        .where(Blocker.resolved_at.is_(None), Blocker.severity.in_(("high", "critical")))
        .distinct()
        .subquery()
    )
    stmt = (
        select(
            User,
            func.count(Client.id.distinct()).label("accounts"),
            func.count(case((Stage.key != "live", Client.id)).distinct()).label("onboarding"),
            func.count(severe.c.client_id.distinct()).label("severe"),
            func.coalesce(func.sum(Client.contract_value), 0).label("contract_value"),
        )
        .outerjoin(Client, Client.owner_id == User.id)
        .outerjoin(Stage, Stage.id == Client.current_stage_id)
        .outerjoin(severe, severe.c.client_id == Client.id)
        .where(User.is_active.is_(True))
        .group_by(User.id)
        .order_by(func.count(Client.id.distinct()).desc(), User.name)
    )
    return [
        OwnerWorkload(u, int(a), int(o), int(s), Decimal(str(cv)))
        for u, a, o, s, cv in db.execute(stmt)
    ]
