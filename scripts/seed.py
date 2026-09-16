"""Populate the database with a realistic, fictional demo dataset.

    python scripts/seed.py            # wipes client data and re-seeds (stages are kept)

Deterministic (fixed Faker seed) so the demo looks the same on every deploy,
but all dates are relative to *today* so the dashboard always looks alive.
Every client below is designed to land on a particular health colour — see
the SCENARIOS table — which gives the demo a believable mix of red/amber/green.
"""

from __future__ import annotations

import random
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path

# Allow `python scripts/seed.py` from the repo root without installing the package.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from faker import Faker  # noqa: E402
from sqlalchemy import delete, select  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.database import SessionLocal  # noqa: E402
from app.models import (  # noqa: E402
    Blocker,
    Client,
    ClientStageHistory,
    Meeting,
    Milestone,
    Note,
    Stage,
    User,
    meeting_attendees,
    utcnow,
)

fake = Faker()
Faker.seed(42)
random.seed(42)

STAGE_ORDER = ["kickoff", "discovery", "uat", "prod", "live"]
# Typical days spent in each *completed* stage, used to back-fill history.
TYPICAL_DAYS = {"kickoff": 7, "discovery": 24, "uat": 18, "prod": 10}

TEAM = [
    ("Maya Okonkwo", "maya.okonkwo@example.com", "manager"),
    ("Daniel Reyes", "daniel.reyes@example.com", "csm"),
    ("Priya Raman", "priya.raman@example.com", "csm"),
    ("Tom Whitfield", "tom.whitfield@example.com", "implementation_analyst"),
    ("Sofia Lindqvist", "sofia.lindqvist@example.com", "implementation_analyst"),
    ("Jae Park", "jae.park@example.com", "engineer"),
]


@dataclass(frozen=True)
class BlockerSpec:
    title: str
    severity: str
    age_days: int
    resolved: bool = False


@dataclass(frozen=True)
class Scenario:
    name: str
    segment: str
    contract_value: int
    stage: str
    days_in_stage: int
    days_to_go_live: int
    overdue_milestones: int = 0
    blockers: tuple[BlockerSpec, ...] = ()
    expected: str = "green"  # documentation only; the engine decides


# 20 fictional fintech / SaaS accounts. "expected" is what the rules should produce.
SCENARIOS: list[Scenario] = [
    # --- red -----------------------------------------------------------------
    Scenario(
        "Ledgerline Capital",
        "enterprise",
        240_000,
        "uat",
        12,
        30,
        0,
        (BlockerSpec("Production SSO metadata rejected by IdP", "critical", 3),),
        "red",
    ),
    Scenario(
        "Northbeam Analytics",
        "mid_market",
        96_000,
        "discovery",
        15,
        45,
        1,
        (BlockerSpec("Client has not delivered custody feed credentials", "high", 11),),
        "red",
    ),
    Scenario(
        "Harborview Asset Mgmt",
        "enterprise",
        310_000,
        "uat",
        26,
        -6,
        2,
        (BlockerSpec("Position reconciliation off by 0.4% on 3 funds", "high", 4),),
        "red",
    ),
    Scenario("Quill & Compass Advisors", "smb", 18_000, "discovery", 40, -2, 1, (), "red"),
    # --- amber ---------------------------------------------------------------
    Scenario("Meridian Trade Desk", "enterprise", 185_000, "uat", 9, 10, 0, (), "amber"),
    Scenario(
        "Copperfield Funds",
        "mid_market",
        72_000,
        "uat",
        24,
        40,
        0,
        (BlockerSpec("Custom report template awaiting sign-off", "medium", 9),),
        "amber",
    ),
    Scenario("Bluefin Payments", "mid_market", 54_000, "discovery", 8, 60, 2, (), "amber"),
    Scenario("Saltmarsh Wealth", "smb", 22_000, "kickoff", 13, 75, 0, (), "amber"),
    Scenario(
        "Orbital Treasury",
        "enterprise",
        265_000,
        "prod",
        16,
        5,
        0,
        (BlockerSpec("Nightly batch window conflicts with client ETL", "high", 5),),
        "amber",
    ),
    Scenario("Tidewater Lending", "mid_market", 88_000, "discovery", 31, 50, 0, (), "amber"),
    # --- green ---------------------------------------------------------------
    Scenario("Acme Brokerage", "smb", 12_000, "kickoff", 3, 70, 0, (), "green"),
    Scenario(
        "Granite Peak Partners",
        "enterprise",
        220_000,
        "discovery",
        12,
        55,
        0,
        (BlockerSpec("Sandbox API rate limit too low", "medium", 2),),
        "green",
    ),
    Scenario(
        "Lumen Insurance Tech",
        "mid_market",
        64_000,
        "uat",
        6,
        28,
        1,
        (
            BlockerSpec("Test user locked out", "low", 1),
            BlockerSpec("UAT env missing FX rates", "high", 20, resolved=True),
        ),
        "green",
    ),
    Scenario("Kestrel Clearing", "enterprise", 198_000, "prod", 4, 6, 0, (), "green"),
    Scenario("Pinewood Family Office", "smb", 15_000, "prod", 9, 3, 0, (), "green"),
    Scenario("Vantage Point Research", "mid_market", 59_000, "live", 45, -40, 0, (), "green"),
    Scenario(
        "Silverline Securities",
        "enterprise",
        275_000,
        "live",
        120,
        -110,
        0,
        (BlockerSpec("Post-launch: duplicate ticker mapping", "medium", 6),),
        "green",
    ),
    Scenario("Marlowe Robo-Advisory", "smb", 9_500, "live", 20, -15, 0, (), "green"),
    Scenario("Ironbridge Fund Services", "mid_market", 81_000, "discovery", 20, 62, 0, (), "green"),
    Scenario(
        "Cobalt Reinsurance",
        "enterprise",
        233_000,
        "uat",
        14,
        35,
        0,
        (BlockerSpec("Waiting on client InfoSec questionnaire", "medium", 12),),
        "green",
    ),
]

MILESTONE_TITLES = {
    "kickoff": ["Kickoff call held", "Project charter signed", "Stakeholder map delivered"],
    "discovery": ["Requirements workshop", "Data mapping spec approved", "SSO configuration"],
    "uat": ["UAT test plan agreed", "UAT sign-off", "Training session delivered"],
    "prod": ["Prod credentials issued", "Go-live readiness review", "Cutover rehearsal"],
    "live": ["Hypercare complete", "30-day health check"],
}

NOTE_TEMPLATES = [
    "Biweekly sync: client confirmed {topic}. Next step is {next_step}.",
    "Follow-up sent to {contact} re: {topic}; awaiting response.",
    "Internal: {topic} needs engineering input before {next_step}.",
    "Client asked to move {next_step} out one week due to {reason}.",
]
TOPICS = [
    "SSO metadata",
    "custody feed mapping",
    "UAT scope",
    "report templates",
    "user provisioning",
    "historical data backfill",
    "go-live checklist",
]
NEXT_STEPS = [
    "UAT kickoff",
    "prod credential hand-off",
    "data validation",
    "training",
    "cutover rehearsal",
    "final sign-off",
]
REASONS = ["quarter-end close", "an internal audit", "a key contact on leave", "vendor delays"]


def wipe(db: Session) -> None:
    """Delete demo data but keep the fixed stages lookup rows."""
    for table in (meeting_attendees,):
        db.execute(delete(table))
    for model in (Meeting, Note, Blocker, Milestone, ClientStageHistory, Client, User):
        db.execute(delete(model))
    db.commit()


def seed_users(db: Session) -> list[User]:
    users = [User(name=n, email=e, role=r) for n, e, r in TEAM]
    db.add_all(users)
    db.flush()
    return users


def build_history(
    client: Client, stages: dict[str, Stage], sc: Scenario, now: datetime, changed_by: User
) -> datetime:
    """Create stage rows back from the current stage; returns the kickoff timestamp."""
    idx = STAGE_ORDER.index(sc.stage)
    entered = now - timedelta(days=sc.days_in_stage)
    rows = [
        ClientStageHistory(
            stage=stages[sc.stage], entered_at=entered, exited_at=None, changed_by=changed_by
        )
    ]
    cursor = entered
    for key in reversed(STAGE_ORDER[:idx]):
        days = TYPICAL_DAYS[key] + random.randint(-3, 3)
        start = cursor - timedelta(days=days)
        rows.append(
            ClientStageHistory(
                stage=stages[key], entered_at=start, exited_at=cursor, changed_by=changed_by
            )
        )
        cursor = start
    client.stage_history.extend(reversed(rows))
    return cursor


def seed_milestones(client: Client, sc: Scenario, now: datetime, owners: list[User]) -> None:
    today = now.date()
    idx = STAGE_ORDER.index(sc.stage)
    # Completed milestones for every stage already passed.
    for key in STAGE_ORDER[:idx]:
        for i, title in enumerate(MILESTONE_TITLES[key]):
            done_on = now - timedelta(days=sc.days_in_stage + 5 * (len(MILESTONE_TITLES[key]) - i))
            client.milestones.append(
                Milestone(
                    title=title,
                    due_date=done_on.date() + timedelta(days=2),
                    completed_at=done_on,
                    status="done",
                    owner=random.choice(owners),
                )
            )
    # Current-stage milestones: the first N are overdue (open, due in the past).
    titles = MILESTONE_TITLES[sc.stage]
    for i, title in enumerate(titles):
        if i < sc.overdue_milestones:
            due = today - timedelta(days=random.randint(2, 12))
            status = "in_progress"
        else:
            due = today + timedelta(days=random.randint(3, 25))
            status = "not_started" if i > 0 else "in_progress"
        client.milestones.append(
            Milestone(title=title, due_date=due, status=status, owner=random.choice(owners))
        )


def seed_blockers(client: Client, sc: Scenario, now: datetime, owners: list[User]) -> None:
    for n, spec in enumerate(sc.blockers, start=1):
        opened = now - timedelta(days=spec.age_days, hours=random.randint(1, 9))
        resolved = (now - timedelta(days=max(spec.age_days - 3, 0))) if spec.resolved else None
        client.blockers.append(
            Blocker(
                title=spec.title,
                description=fake.paragraph(nb_sentences=2),
                severity=spec.severity,
                owner=random.choice(owners),
                opened_at=opened,
                resolved_at=resolved,
                external_ref=f"IMPL-{100 + client_seq(client) * 3 + n}",
                milestone=random.choice(client.milestones) if client.milestones and n % 2 else None,
            )
        )


_seq: dict[str, int] = {}


def client_seq(client: Client) -> int:
    return _seq.setdefault(client.name, len(_seq) + 1)


def seed_notes_and_meetings(client: Client, now: datetime, team: list[User]) -> None:
    for k in range(random.randint(2, 4)):
        when = now - timedelta(days=14 * k + random.randint(0, 3), hours=random.randint(1, 8))
        client.notes.append(
            Note(
                body=random.choice(NOTE_TEMPLATES).format(
                    topic=random.choice(TOPICS),
                    next_step=random.choice(NEXT_STEPS),
                    contact=fake.first_name(),
                    reason=random.choice(REASONS),
                ),
                author=random.choice(team),
                created_at=when,
            )
        )
        meeting = Meeting(
            held_at=when.replace(minute=0, second=0, microsecond=0),
            summary=f"Biweekly implementation sync — {random.choice(TOPICS)} reviewed.",
            action_items=(
                f"- Client: {random.choice(NEXT_STEPS)}\n- Us: {random.choice(NEXT_STEPS)}"
            ),
        )
        meeting.attendees = random.sample(team, k=random.randint(2, 3))
        client.meetings.append(meeting)


def run() -> None:
    now = utcnow()
    with SessionLocal() as db:
        stages = {s.key: s for s in db.scalars(select(Stage)).all()}
        if set(stages) != set(STAGE_ORDER):
            raise SystemExit("Stages table is empty or wrong — run `alembic upgrade head` first.")

        wipe(db)
        team = seed_users(db)
        csms = [u for u in team if u.role in ("csm", "implementation_analyst")]

        for sc in SCENARIOS:
            client = Client(
                name=sc.name,
                segment=sc.segment,
                contract_value=Decimal(sc.contract_value),
                owner=random.choice(csms),
                current_stage=stages[sc.stage],
                target_go_live_date=now.date() + timedelta(days=sc.days_to_go_live),
                kickoff_date=now.date(),  # placeholder, fixed below from history
            )
            kickoff_ts = build_history(client, stages, sc, now, changed_by=client.owner)
            client.kickoff_date = kickoff_ts.date()
            client.created_at = kickoff_ts
            seed_milestones(client, sc, now, csms)
            seed_blockers(client, sc, now, team)
            seed_notes_and_meetings(client, now, team)
            db.add(client)

        db.commit()

        print(
            f"Seeded {len(team)} users, {len(SCENARIOS)} clients, "
            f"{db.query(Milestone).count()} milestones, {db.query(Blocker).count()} blockers, "
            f"{db.query(Note).count()} notes, {db.query(Meeting).count()} meetings."
        )


if __name__ == "__main__":
    run()
