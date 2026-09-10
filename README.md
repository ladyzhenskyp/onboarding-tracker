# Client Onboarding & Implementation Tracker

A lightweight web app for customer-success / implementation teams. Each client
account moves through a fixed onboarding pipeline
(**Kickoff → Discovery/Config → UAT → Prod → Live**) and the team can see at a
glance which accounts are at risk — and *why*.

> Status: Phase 0 (design). See `docs/` for the ERD, schema notes and the
> at-risk rules spec.

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
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# (Phase 1+) alembic upgrade head && python scripts/seed.py
# (Phase 2+) uvicorn app.main:app --reload
```
