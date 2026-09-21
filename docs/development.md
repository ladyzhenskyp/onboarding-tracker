# Developer guide

## Setup

```bash
git clone https://github.com/ladyzhenskyp/onboarding-tracker.git
cd onboarding-tracker
python3.12 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
alembic upgrade head        # creates tracker.db (SQLite) with all tables + the 5 stages
python scripts/seed.py      # 20 fictional clients; safe to re-run, it wipes and reseeds
uvicorn app.main:app --reload
```

Open http://127.0.0.1:8000. `--reload` restarts the server when a `.py` file
changes; template edits are picked up on the next request without a restart.

## Everyday commands

| Task | Command |
|---|---|
| Run all tests | `pytest` |
| Run one file / one test | `pytest tests/test_risk.py` · `pytest -k critical` |
| Lint | `ruff check .` (add `--fix` to auto-fix imports etc.) |
| Format | `ruff format .` |
| Reset the demo database | `python scripts/seed.py` |
| Start from an empty database | `rm tracker.db && alembic upgrade head && python scripts/seed.py` |

Tests use their own throwaway SQLite file (see `tests/conftest.py`), so they
never touch `tracker.db`.

## Project layout

```
app/
  main.py            FastAPI app: mounts routers and /static, /healthz
  config.py          Settings from environment / .env
  database.py        Engine, session factory, get_db dependency
  deps.py            Templates + Jinja filters (money, date, humanize), get_now, get_risk_config
  models/            One file per table (SQLAlchemy 2.0 mapped classes)
  services/
    risk.py          Rule engine (pure functions) + ORM bridge
    stages.py        Stage transitions (one transaction)
    actions.py       Add/resolve blocker, add/complete milestone, add note
    queries.py       ORM versions of the analytical SQL
  routers/           dashboard, pipeline, clients, blockers, team, exports
  templates/         Jinja2: base.html (tokens, components, sort script), one file per page,
                     clients/_body.html = the HTMX-swappable region
  risk_rules.yaml    Thresholds
alembic/             Migrations (env.py reads DATABASE_URL from settings)
db/schema.sql        Canonical DDL (PostgreSQL dialect)
queries/*.sql        Reviewable analytical SQL (PostgreSQL dialect)
scripts/seed.py      Demo data
tests/               conftest.py (seeded test DB), test_risk.py, test_routes.py
docs/                This folder
```

## Conventions

- **Routers stay thin.** Parse the request, call a service, choose a response.
  If you find yourself writing an `if` about business rules in a router, move
  it to `app/services/`.
- **Services take a `Session` and commit.** They don't know about HTTP.
- **Derived values are computed, not stored** (health, overdue, open). Add a
  property or a service function; don't add a column.
- **Time is injected.** Routes get `now` from `get_now()`; the risk engine takes
  `now` as an argument. Tests can freeze it.
- **Every table is `class="sortable"`** with `.th` / `.th-l` / `.num` / `.tc`
  header and cell classes (see `base.html`) so alignment stays consistent.
- Keep code compatible with Python 3.10+ (`timezone.utc`, no `datetime.UTC`).

## How to…

### Change a risk threshold
Edit `app/risk_rules.yaml` and restart the server. Unknown stage keys fail at
startup on purpose. Add a test case to `tests/test_risk.py` if the behaviour
matters.

### Add a new risk rule
1. Describe it in `docs/risk-rules.md` (condition, colour, message).
2. Add the check in `evaluate()` in `app/services/risk.py`, appending a
   `RuleHit(rule_id, colour, message)`.
3. If it needs a new input, extend `ClientSnapshot` and `snapshot_from_client`.
4. Add cases to `tests/test_risk.py` (positive, boundary, negative).
5. Mirror it in `queries/at_risk_accounts.sql` so the SQL and Python agree.
6. Add a short label for it in the `short` map in `app/templates/pipeline.html`.

### Add a column to a table
1. Add it to the model in `app/models/…` **and** to `db/schema.sql`.
2. Generate a migration: `alembic revision --autogenerate -m "add priority to blockers"`
   and read the generated file before applying it.
3. `alembic upgrade head`.
4. Update the seed script if demo data should populate it.

### Add a page
1. Create `app/routers/<name>.py` with an `APIRouter`; register it in `app/main.py`.
2. Add `app/templates/<name>.html` extending `base.html`; use the macros in
   `partials/macros.html` for badges, chips and section titles.
3. Add a nav link in `base.html` and a test in `tests/test_routes.py`.

### Add an HTMX action to the client page
1. Add the service function in `app/services/actions.py`.
2. Add a `@router.post` in `app/routers/clients.py` that calls it and returns
   `_after_action(request, db, client_id, now, cfg)`.
3. Add the form in `clients/_body.html` with both `hx-post`/`hx-target`/`hx-swap`
   **and** `method`/`action`, so it works without JavaScript too.

## Deploying

`Dockerfile` + `scripts/start.sh` are the whole deployment story; `railway.json`
adds a health check. Push to `main` and Railway rebuilds. To try the container
locally:

```bash
docker build -t onboarding-tracker .
docker run --rm -p 8000:8000 -e SECRET_KEY=dev -e DATABASE_URL=sqlite:////tmp/tracker.db onboarding-tracker
```

CI (`.github/workflows/ci.yml`) runs ruff, pytest and a migration + seed smoke
test on every push and pull request.

## Verifying the SQL against PostgreSQL

The `.sql` files and the migration are written for PostgreSQL. To check them
locally you need a Postgres instance (Docker: `docker run -e POSTGRES_PASSWORD=pw -p 5432:5432 postgres:16`):

```bash
export DATABASE_URL=postgresql://postgres:pw@localhost:5432/postgres
alembic upgrade head && python scripts/seed.py
psql "$DATABASE_URL" -v today="'$(date +%F)'" -v now="'$(date '+%F %H:%M')'" \
     -v high_blocker_days=7 -v overdue_threshold=2 -v go_live_warning_days=14 \
     -f queries/at_risk_accounts.sql
```

## Troubleshooting

| Symptom | Cause / fix |
|---|---|
| `ModuleNotFoundError: app` when running `alembic` or `scripts/seed.py` | Run from the repo root with the venv active. |
| `Stages table is empty` from the seed script | Run `alembic upgrade head` first. |
| A new Tailwind class has no effect | Run `python scripts/build_css.py` (needs Node) and commit `app/static/vendor/tailwind.css`. |
| A test fails with `database is locked` | Another process has `tracker.db` open; tests use their own file, but stop the dev server if in doubt. |
| `if>` prompt in the terminal after pasting commands | zsh treated a `#` comment as a command. Press Ctrl‑C and paste commands without comments. |

## Demo reset

The live site is a shared demo, so it puts its own data back every hour, on the hour: a background task
(`app/services/demo_reset.py`) wipes and re-seeds, and the container also resets on every start.
Set `DEMO_RESET_SCHEDULE=nightly` to reset once a day instead, at `DEMO_RESET_HOUR_UTC` (default 8,
which is 4am in New York). Wipe and seed run in one transaction and
row ids restart at 1, so visitors never see an empty app and links like `/clients/1` keep working.

It is off by default (`DEMO_RESET_NIGHTLY=false`), so running locally never wipes your data;
`scripts/start.sh` switches it on inside the container. To keep data on a deployment, set
`DEMO_RESET_NIGHTLY=false` in the service's variables.
