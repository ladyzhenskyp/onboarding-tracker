# Schema design notes

This is the "why" behind `db/schema.sql`. These are the decisions most likely
to come up in an interview.

## 1. Normalization: what is a table and what is a column

The rule I applied: **a thing gets its own table when it can occur more than
once per parent, or when it needs to be joined/filtered on its own.**

| Concept                | Decision                | Reason                                                                 |
|------------------------|-------------------------|------------------------------------------------------------------------|
| Team member            | `users` table           | Referenced from 6 places; a person's name/role must live in one row.   |
| Pipeline stage         | `stages` lookup table   | Ordered, joinable, extensible without a migration (see §2).            |
| Stage membership       | `client_stage_history`  | A client visits many stages over time; we need timestamps per visit.   |
| Milestone / Blocker / Note / Meeting | Own tables | One-to-many from client.                                            |
| Meeting attendees      | `meeting_attendees`     | Many-to-many needs a junction table; composite PK prevents duplicates. |
| Segment, severity, role, status | `VARCHAR + CHECK` | Small closed sets that never need extra attributes → column, not table. |
| Health status          | **not stored**          | Derived; storing it would go stale the moment a blocker ages a day.    |

The schema is in **3NF**: every non-key column depends on the key, the whole
key, and nothing but the key. The one deliberate denormalization is
`clients.current_stage_id` (§3).

## 2. `stages` as a lookup table vs. an enum

An enum (`CHECK (stage IN (...))`) would have been simpler, but a lookup
table gives three things an enum can't:

1. **Ordering lives in data** (`sort_order`), so the Kanban board is
   `ORDER BY stages.sort_order` instead of a hard-coded list in Python.
2. **Human labels live in data** (`name`), so "Discovery / Configuration"
   is not scattered across templates.
3. **Aggregation is a JOIN**: "count of clients per stage" is a plain
   `GROUP BY` that returns zero-count stages too (LEFT JOIN from `stages`).

The small enum-like columns (`severity`, `segment`, `role`, milestone
`status`) stay as `CHECK` constraints because they carry no extra attributes
and I want `schema.sql` to run unchanged on SQLite and Postgres.

## 3. Why stage history is its own table (and why `current_stage_id` still exists)

If `clients` only had a `stage` column we could show *where* an account is
but never *how long it has been there* or *how long UAT usually takes*.
`client_stage_history` records one row per stage visit with `entered_at` /
`exited_at`, which gives us:

- **time in current stage**: `now() - entered_at` for the row with
  `exited_at IS NULL` — one of the risk-rule inputs;
- **average duration per stage** across all clients (dashboard metric);
- **an audit trail** — who advanced the client and when (`changed_by_id`),
  including moves backwards (Prod → UAT after a failed release).

`clients.current_stage_id` is a **denormalised copy** of the open history
row's `stage_id`. It exists purely so the pipeline board and list views can
filter by stage with one indexed lookup instead of a correlated subquery.
Integrity is protected two ways:

- the service layer writes both rows in **one transaction** when a stage
  changes (close old history row, open new one, update the pointer);
- the partial unique index `ux_stage_history_open (client_id) WHERE exited_at IS NULL`
  makes it **impossible** for a client to have two "current" stages.

## 4. Derived vs. stored status

- **Milestone "Overdue"** is not a value of `status`. It is
  `status <> 'done' AND due_date < CURRENT_DATE`. If it were stored, a
  nightly job would have to flip it and it would be wrong between runs.
- **Blocker "open/closed"** is `resolved_at IS NULL`. One column instead of
  a boolean plus a timestamp that could disagree with each other.
- **Client health** is computed by the risk engine (`docs/risk-rules.md`)
  from the rows above at query time.

The `CHECK ((status = 'done') = (completed_at IS NOT NULL))` on milestones
enforces that "done" and "has a completion timestamp" can never disagree.

## 5. Foreign keys and delete behaviour

| FK                                   | On delete    | Reason                                                              |
|--------------------------------------|--------------|---------------------------------------------------------------------|
| child → `clients`                    | `CASCADE`    | Deleting a client removes its history, milestones, blockers, notes. |
| `blockers.milestone_id`              | `SET NULL`   | A blocker outlives its milestone; it just becomes client-level.     |
| `*.owner_id`, `author_id` → `users`  | default (RESTRICT) | You should deactivate a user (`is_active = false`), not delete them. |
| `meeting_attendees.*`                | `CASCADE`    | Junction rows are meaningless without either parent.                |

## 6. Indexes

Every foreign key is indexed (Postgres does **not** do this automatically;
without them every `JOIN` on `client_id` is a sequential scan). Beyond that,
three **partial indexes** target the hot paths:

| Index                     | Covers                                         | Used by                     |
|---------------------------|------------------------------------------------|-----------------------------|
| `ux_stage_history_open`   | one open history row per client (also a constraint) | time-in-stage, stage change |
| `ix_milestones_open_due`  | open milestones by due date                    | overdue-milestone rule, dashboard panel |
| `ix_blockers_open`        | open blockers by client, severity, age         | critical/high blocker rules |

Partial indexes are small (only open rows) and exactly match the `WHERE`
clauses the risk engine uses.

## 7. Data types

- `NUMERIC(12,2)` for money — never `FLOAT` (rounding errors in currency).
- `DATE` for business dates (kickoff, go-live, due) and `TIMESTAMP` for
  events (entered/exited/opened/resolved). Comparing a date to "today" is
  unambiguous; comparing a timestamp to "today" depends on time zone.
- Timestamps are stored **naive UTC**; the app layer treats them as UTC.
  (Postgres `TIMESTAMPTZ` would be stricter, but SQLite has no such type
  and keeping the two environments identical matters more here.)

## 8. What I would change at scale

- Move timestamps to `TIMESTAMPTZ` once SQLite is dropped.
- Cache health status in a materialised view refreshed on write, once the
  at-risk query stops being fast enough to compute on every dashboard load.
- Add a `tenants`/`organizations` table if more than one CS team used it.
