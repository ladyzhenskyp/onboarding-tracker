# Client Onboarding & Implementation Tracker

[![CI](https://github.com/ladyzhenskyp/onboarding-tracker/actions/workflows/ci.yml/badge.svg)](https://github.com/ladyzhenskyp/onboarding-tracker/actions/workflows/ci.yml)

A lightweight web app for customer-success / implementation teams. Each client
account moves through a fixed onboarding pipeline
(**Kickoff → Discovery/Config → UAT → Prod → Live**) and the team can see at a
glance which accounts are at risk — and *why*.

> **Live demo:** https://onboarding-tracker-production-0880.up.railway.app — sign in
> with the pre-filled demo account. Data is fictional and reseeds on deploy.
>
> Status: deployed on Railway (Docker + Postgres), CI on every push.

## Stack

| Layer      | Choice                                   | Why                                                      |
|------------|------------------------------------------|----------------------------------------------------------|
| Backend    | Python 3.12, FastAPI                     | Typed, fast, easy to explain; Python already on resume   |
| Database   | PostgreSQL (prod) / SQLite (local)       | SQL and schema design are first-class in this project    |
| ORM        | SQLAlchemy 2.0 + Alembic migrations      | Industry standard; hand-written `db/schema.sql` kept too |
| Frontend   | Jinja2 templates + HTMX + Tailwind CSS   | No separate JS build; inline updates without React       |
| Charts     | Chart.js                                 | Small, no build step                                     |
| Tests / CI | pytest, ruff, GitHub Actions             |                                                          |
| Deploy     | Docker → Railway (Hobby) + Postgres      | Always-on, no cold starts; deploys on push               |

## Deployment

The app ships as a Docker image (`Dockerfile`). On start, `scripts/start.sh`
runs `alembic upgrade head`, seeds demo data if the database is empty, then
serves with uvicorn on `$PORT`.

Railway (used for the live demo): create a project from this repo, add a
**PostgreSQL** service, and set these variables on the web service:

| Variable | Value |
|---|---|
| `DATABASE_URL` | `${{ Postgres.DATABASE_URL }}` (reference the Postgres service) |
| `PORT` | set by Railway automatically (8080); point the public domain at the same port |
| `SECRET_KEY` | any long random string (`python -c "import secrets; print(secrets.token_hex(32))"`) |
| `DEMO_USERNAME` / `DEMO_PASSWORD` | the shared demo login |
| `SEED_ON_DEPLOY` | `true` (default) — seeds only when there are no clients |

`railway.json` points the health check at `/healthz`. Any Docker host works the
same way; only the `DATABASE_URL` differs.

To reset the demo data on a running deployment, run `python scripts/seed.py`
in the service's shell (it wipes client data and reseeds; stages are kept).

## Authentication

A single demo account guards every page so the public demo can't be edited
anonymously. It is intentionally minimal — a signed session cookie checked by
a middleware (`app/auth.py`). A real deployment would use per-user accounts and
SSO; see `docs/architecture.md`.

## Documentation

| Doc | What it covers |
|---|---|
| [`docs/architecture.md`](docs/architecture.md) | Request flow, the three layers, why each tool, key design decisions |
| [`docs/user-guide.md`](docs/user-guide.md) | The pipeline, how health is computed, each page, working an account |
| [`docs/schema-design.md`](docs/schema-design.md) | Normalisation, lookup tables vs enums, stage history, indexes |
| [`docs/erd.md`](docs/erd.md) | Entity-relationship diagram |
| [`docs/risk-rules.md`](docs/risk-rules.md) | The at-risk rules spec and test cases |
| [`docs/development.md`](docs/development.md) | Setup, commands, conventions, how to add rules/columns/pages, deploying |
| [`docs/glossary.md`](docs/glossary.md) | Plain-language definitions of every term above |
| [`queries/README.md`](queries/README.md) | The hand-written analytical SQL |

## Repo layout

```
app/            FastAPI application (models, routers, services, templates)
db/schema.sql   Hand-written DDL — the source of truth for the data model
queries/        Reviewable analytical SQL (at-risk, time-in-stage, workload)
docs/           Architecture, user guide, schema design, ERD, risk rules, dev guide, glossary
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
