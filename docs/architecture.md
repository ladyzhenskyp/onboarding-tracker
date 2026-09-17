# Architecture

How a request moves through the app, what each layer is responsible for, and
why each tool was chosen. Read this before `schema-design.md` and
`risk-rules.md` if you are new to the codebase.

## One request, end to end

Opening a client's page (`GET /clients/7`) touches every layer once:

```
Browser ──GET /clients/7──▶ FastAPI router (app/routers/clients.py)
                                │  asks for the client, with its history, blockers, milestones
                                ▼
                            SQLAlchemy (app/models/)  ──SELECT …──▶  PostgreSQL / SQLite
                                │  returns a Client object
                                ▼
                            Risk engine (app/services/risk.py)
                                │  computes red / amber / green + reasons
                                ▼
                            Jinja2 template (app/templates/clients/detail.html)
                                │  fills placeholders with the object's values
                                ▼
Browser ◀──finished HTML────  FastAPI
```

Nothing is computed in the browser. The page arrives complete ("server-rendered").
When the user clicks an action button (advance stage, resolve blocker…), HTMX
sends the same kind of request in the background and swaps only the part of the
page that changed — see *Frontend* below.

## The three layers

| Layer | Folder | Responsibility | Knows about |
|---|---|---|---|
| **Routers** | `app/routers/` | Receive the HTTP request, pull out IDs and form fields, call a service, choose the response (page, fragment, redirect, CSV). Thin by design. | Services, templates |
| **Services** | `app/services/` | Business rules: how a stage change works, what "at risk" means, the analytical queries. Plain Python functions that take a database session. | Models |
| **Models** | `app/models/` | One class per table. Columns, constraints, relationships. Mirrors `db/schema.sql`. | The database |

Templates (`app/templates/`) are the fourth piece: they decide how the data
looks and contain no business logic.

Keeping the rules out of the routers is what makes them testable without a web
server: `tests/test_risk.py` calls the risk engine directly with hand-built
inputs; `tests/test_routes.py` then checks the pages on top.

## Why each tool

**FastAPI** — a small, typed Python web framework. Route functions declare what
they need (`client_id: int`, `db: Session = Depends(get_db)`) and FastAPI
supplies it. Python was already on the resume; the framework adds little to learn.

**SQLAlchemy 2.0 (ORM)** — maps tables to Python classes so the app can say
`db.get(Client, 7)` instead of writing `SELECT` by hand, and runs unchanged on
SQLite locally and PostgreSQL in production. The analytical SQL that *is* worth
reading by hand lives in `queries/` as plain `.sql` files, with ORM equivalents
in `app/services/queries.py`.

**Alembic** — version control for the database's structure. `db/schema.sql`
shows the complete design; migrations in `alembic/versions/` are the ordered,
replayable steps that get a real database (with data in it) to that design.

**Jinja2** — templates: HTML with holes. `{{ client.name }}` and
`{% for m in client.milestones %}` are filled in on the server.

**HTMX** — two attributes on a form (`hx-post`, `hx-target`) turn a full-page
form submit into a background request whose HTML response replaces one region
of the page. This gives "single-page app" feel with zero client-side state and
no JavaScript build. The alternative (React + a JSON API) would have doubled
the codebase for a project whose substance is the data model.

**Tailwind CSS** — utility classes, loaded from a CDN so there is no build step.
Design tokens (colours, fonts) are declared once in `base.html`. A production
deployment would precompile Tailwind; for a portfolio demo the CDN is the
right trade-off and is noted in the template.

**Chart.js** — three small charts on the dashboard; data is embedded as JSON
by the route, so charts and tables always agree.

**pytest + ruff** — tests and lint/format. CI (Phase 4) runs both on every push.

## Key design decisions

Each of these has a longer write-up in `schema-design.md`.

1. **Pipeline stages are a lookup table**, not an enum, so ordering and labels
   live in data and "count per stage" is a plain `GROUP BY`.
2. **Stage history is its own table** (`client_stage_history`) with
   entered/exited timestamps. Time-in-stage, per-stage averages and an audit
   trail all fall out of it. `clients.current_stage_id` is a deliberate,
   transaction-protected shortcut to the open row.
3. **Health is computed, never stored.** `app/services/risk.py` evaluates each
   client against `app/risk_rules.yaml` at read time and reports *every* rule
   that fired, so the UI can say why. Storing a colour would go stale the
   moment a blocker aged a day.
4. **"Overdue" and "open" are derived too** (`due_date < today AND status <> 'done'`;
   `resolved_at IS NULL`). One column, no drift.
5. **Advancing a stage is not gated.** The tool records what the team says
   happened and makes risk visible afterwards, rather than refusing to advance
   with open items — the same choice JIRA and Redmine make by default.

## Frontend pattern (HTMX)

`app/templates/clients/detail.html` is a thin page that includes
`clients/_body.html`, the region that can change. Every form in `_body.html`
carries both:

```html
<form hx-post="/clients/7/stage/advance" hx-target="#client-body" hx-swap="outerHTML"
      method="post" action="/clients/7/stage/advance">
```

With JavaScript, HTMX sends the request and swaps the returned fragment. Without
it, the browser submits the form normally and the server redirects. The router
decides which to send by checking the `HX-Request` header
(`_after_action` in `app/routers/clients.py`).

## Configuration

Everything configurable is read once in `app/config.py` from environment
variables (a local `.env` for development, real env vars in production):

| Variable | Purpose |
|---|---|
| `DATABASE_URL` | `sqlite:///./tracker.db` locally; a `postgresql://` URL on Render |
| `RISK_RULES_PATH` | YAML file of thresholds (default `app/risk_rules.yaml`) |
| `SECRET_KEY`, `DEMO_USERNAME`, `DEMO_PASSWORD` | Demo login (Phase 4) |

## What I would change at scale

- Precompile Tailwind and pin HTMX/Chart.js locally instead of CDNs.
- Cache health results (materialised view or a nightly job) once the at-risk
  query stops being cheap enough to run on every dashboard load.
- Move timestamps to `TIMESTAMPTZ` once SQLite is dropped.
- Add an organisation/tenant table if more than one team used it.
