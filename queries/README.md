# Analytical SQL

Hand-written, reviewable SQL for the queries the app depends on. Each file
has a header comment describing inputs and the shape of the result. ORM
equivalents live in `app/services/`. Written to run on both PostgreSQL and
SQLite unless noted.

- `at_risk_accounts.sql`   — health colour + reason per client (Phase 1)
- `time_in_stage.sql`      — days in current stage and average per stage (Phase 1)
- `overdue_milestones.sql` — open milestones past due date (Phase 1)
- `owner_workload.sql`     — accounts and at-risk accounts per owner (Phase 1)
