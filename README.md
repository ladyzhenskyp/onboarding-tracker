# Client Onboarding & Implementation Tracker

A lightweight web app for customer-success / implementation teams. Each client
account moves through a fixed onboarding pipeline
(**Kickoff → Discovery/Config → UAT → Prod → Live**) and the team can see at a
glance which accounts are at risk — and *why*.

> Status: Phase 2 complete — working web app (dashboard, pipeline board, client
> detail with actions, blockers, team view, CSV export). Styling, HTMX and
> deployment are next.

## Stack

| Layer      | Choice                                   | Why                                                      |
|------------|------------------------------------------|----------------------------------------------------------|
| Backend    | Python 3.12, FastAPI                     | Typed, fast, easy to explain; Python already on resume   |
| Database   | PostgreSQL (prod) / SQLite (local)       | SQL and schema design are first-class in this project    |
| ORM        | SQLAlchemy 2.0 + Alembic migrations      | Industry standard; hand-written `db/schema.sql` kept too |
| Frontend   | Jinja2 templates + HTMX + Tailwind CSS   | No separate JS build; inline updates without React       |
| Charts     | Chart.js                                 | Small, no build step                                     |
| Tests / CI | pytest, ruff, GitHub Actions             |                                                          |
| Deploy     | Docker → Render (free tier) + Postgres   |                                                          |

## Repo layout

```
app/            FastAPI application (models, routers, services, templates)
db/schema.sql   Hand-written DDL — the source of truth for the data model
queries/        Reviewable analytical SQL (at-risk, time-in-stage, workload)
docs/           ERD, schema design notes, risk-rules spec
alembic/        Migrations
scripts/        Seed script and utilities
tests/          pytest suite
```

## Running locally

```bash
python3.12 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # defaults to a local SQLite file, tracker.db
alembic upgrade head          # create the tables
python scripts/seed.py        # 20 fictional clients with a realistic risk mix
pytest                        # risk-engine tests
ruff check . && ruff format --check .
```

Then start the server and open http://127.0.0.1:8000:

```bash
uvicorn app.main:app --reload
```

| Page | URL |
|------|-----|
| Dashboard — counts, at-risk list with reasons, upcoming go-lives, overdue milestones, oldest blockers | `/` |
| Pipeline board — one column per stage | `/pipeline` |
| Client detail — stage timeline, milestones, blockers, notes, meetings; advance/move stage, add/resolve blockers, add milestones and notes | `/clients/{id}` |
| Blockers — filter by status, severity, owner, client | `/blockers` |
| Team — workload and health per owner | `/team` |
| CSV export | `/export/pipeline.csv`, `/export/blockers.csv` |

## How health is computed

Health is never stored. `app/services/risk.py` evaluates each client against
the rules in [`docs/risk-rules.md`](docs/risk-rules.md) using thresholds from
[`app/risk_rules.yaml`](app/risk_rules.yaml), and reports every rule that
fired so the UI can say *why* an account is red or amber. The same logic is
expressed as reviewable SQL in [`queries/at_risk_accounts.sql`](queries/at_risk_accounts.sql).
