# Glossary

Plain-language definitions of the terms used in this project, in roughly the
order you meet them.

**Class / object / attribute** — A class is a template (the header row of a
spreadsheet: every client has a name, a segment, a contract value). An object
is one filled-in row made from it. An attribute is one cell: `acme.name`.
A method is an action attached to the template, run against one object's data:
`blocker.age_days(now)`.

**ORM (object-relational mapper)** — A library (here, SQLAlchemy) that keeps a
database table and a Python class lined up. Ask it for row 7 and it runs the
`SELECT` and hands back a `Client` object; change the object and commit and it
writes the `UPDATE`. It translates in both directions; it is not automatic —
you write the class and tell it which table it maps to.

**Model** — SQLAlchemy's word for one of those table classes. `app/models/`.

**Session** — The object that holds a database connection and tracks the changes
you make until you call `commit()`. One per request.

**Migration** — A small, ordered script that changes the database's *structure*
("add column X"), with an undo. Alembic runs them in sequence and remembers
which have been applied. Needed because a live database has data in it, so you
can't just re-run `CREATE TABLE`.

**`schema.sql`** — The complete, hand-written picture of the tables. Migrations
are the steps; the schema file is the destination.

**Router** — A file of route functions: "when a request arrives at this URL,
run this." The front desk of the app. `app/routers/`.

**Service** — A plain Python function containing a business rule ("how does a
stage change work?"). Called by routers; knows nothing about HTTP. `app/services/`.

**Dependency (`Depends`)** — FastAPI's way of handing a route function the
things it needs (a database session, the current time, the risk config)
without the function constructing them itself.

**Template** — An HTML file with holes. Jinja2 fills `{{ client.name }}` from
the object it is given and returns finished HTML. Mail merge for web pages.

**Server-rendered** — The page is completed on the server and the browser just
displays it. The alternative (React) sends raw data and builds the page in the
browser.

**HTMX** — A small library that lets a form or button send its request in the
background and swap the returned HTML into one part of the page instead of
reloading everything. Two attributes: `hx-post` (where) and `hx-target` (which
part to replace).

**Fragment / partial** — A template that renders only a piece of a page, for
HTMX to swap in. `clients/_body.html`.

**Transaction** — A group of database changes that succeed or fail together.
A stage change touches four rows; wrapping them in one transaction means there
is no moment where the history is half-updated.

**Denormalisation** — Deliberately storing a value that could be derived, for
speed. `clients.current_stage_id` duplicates what the open stage-history row
says; the transaction above keeps them in sync.

**Derived value** — Something computed when needed rather than stored: health
colour, "overdue", "open". Can't go stale.

**Partial index** — A database index over only the rows matching a condition
(e.g. `WHERE resolved_at IS NULL`). Small and exactly matches the queries the
risk engine runs.

**Lookup table** — A small table of fixed reference rows (`stages`) that other
rows point at, instead of a hard-coded list in the code.

**Blocker** — A problem stopping or threatening an implementation, tracked as
its own record with severity, owner, open/resolved dates and a ticket reference.
Different from a milestone, which is planned work with a due date.

**Seed script** — `scripts/seed.py`: fills the database with realistic fictional
demo data. Deterministic (same names every run), dated relative to today.

**Fixture** (tests) — Setup code pytest runs before tests: here, a throwaway
seeded database and a test client that can request pages without a server.

**Linter / formatter (ruff)** — Tools that flag likely mistakes and enforce a
consistent code style. CI runs them on every push.
