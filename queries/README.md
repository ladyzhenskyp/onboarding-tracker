# Analytical SQL

Hand-written, reviewable SQL for the queries the app depends on. Each file
has a header comment listing its parameters. These are written for
**PostgreSQL** (the production database); the app itself uses the
dialect-neutral ORM versions in `app/services/queries.py` so the same code
runs on SQLite locally.

| File                     | Question it answers                                            |
|--------------------------|----------------------------------------------------------------|
| `at_risk_accounts.sql`   | Which clients are red/amber/green, and why? (mirrors the rule engine) |
| `time_in_stage.sql`      | How long has each client been in its stage; what's the average per stage? |
| `overdue_milestones.sql` | Which open milestones are past due, and by how much?           |
| `owner_workload.sql`     | How many accounts (and severe blockers) does each owner carry? |

Run one against a local Postgres with, for example:

```bash
psql "$DATABASE_URL" -v today="'2026-09-15'" -v now="'2026-09-15 12:00'" -f queries/overdue_milestones.sql
```

(psql uses `:today` syntax for variables; the app binds the same names.)
