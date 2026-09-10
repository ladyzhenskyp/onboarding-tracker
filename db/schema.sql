-- =============================================================================
-- Client Onboarding & Implementation Tracker — canonical schema
-- Dialect: PostgreSQL 16 (production). SQLite is used locally via Alembic;
-- the only PG-specific syntax here is GENERATED ... AS IDENTITY, which
-- Alembic/SQLAlchemy translate for SQLite automatically.
--
-- Design principles (see docs/schema-design.md for the full walkthrough):
--   * Health status and "overdue" are DERIVED, never stored — see queries/.
--   * Stage history is its own table so time-in-stage is auditable.
--   * Enum-like columns use CHECK constraints for portability.
--   * Every FK is indexed; "open" rows use partial indexes.
-- =============================================================================

-- ---------- Team members -----------------------------------------------------
CREATE TABLE users (
    id          INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name        VARCHAR(120) NOT NULL,
    email       VARCHAR(255) NOT NULL UNIQUE,
    role        VARCHAR(30)  NOT NULL
                CHECK (role IN ('csm', 'implementation_analyst', 'engineer', 'manager')),
    is_active   BOOLEAN      NOT NULL DEFAULT TRUE,
    created_at  TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- ---------- Pipeline stages (lookup table, fixed + ordered) ------------------
-- A lookup table rather than an enum so the pipeline is a real relation:
-- you can JOIN it, ORDER BY sort_order, and add a stage without a migration.
CREATE TABLE stages (
    id          INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    key         VARCHAR(30)  NOT NULL UNIQUE,   -- 'kickoff', 'discovery', ...
    name        VARCHAR(60)  NOT NULL,          -- 'Discovery / Configuration'
    sort_order  SMALLINT     NOT NULL UNIQUE
);

INSERT INTO stages (key, name, sort_order) VALUES
    ('kickoff',   'Kickoff',                   1),
    ('discovery', 'Discovery / Configuration', 2),
    ('uat',       'UAT',                       3),
    ('prod',      'Prod',                      4),
    ('live',      'Live',                      5);

-- ---------- Clients ----------------------------------------------------------
CREATE TABLE clients (
    id                  INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name                VARCHAR(160)  NOT NULL UNIQUE,
    segment             VARCHAR(20)   NOT NULL
                        CHECK (segment IN ('enterprise', 'mid_market', 'smb')),
    contract_value      NUMERIC(12,2) NOT NULL CHECK (contract_value >= 0),
    kickoff_date        DATE          NOT NULL,
    target_go_live_date DATE          NOT NULL,
    owner_id            INTEGER       NOT NULL REFERENCES users(id),
    -- Denormalised pointer to the open row in client_stage_history.
    -- Kept in sync by the service layer inside the same transaction.
    current_stage_id    INTEGER       NOT NULL REFERENCES stages(id),
    created_at          TIMESTAMP     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at          TIMESTAMP     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (target_go_live_date >= kickoff_date)
);

CREATE INDEX ix_clients_owner_id         ON clients(owner_id);
CREATE INDEX ix_clients_current_stage_id ON clients(current_stage_id);
CREATE INDEX ix_clients_target_go_live   ON clients(target_go_live_date);

-- ---------- Stage history (one row per stage visit) --------------------------
-- exited_at IS NULL  => this is the client's current stage.
-- Time in stage = COALESCE(exited_at, now()) - entered_at.
CREATE TABLE client_stage_history (
    id            INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    client_id     INTEGER   NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
    stage_id      INTEGER   NOT NULL REFERENCES stages(id),
    entered_at    TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    exited_at     TIMESTAMP,
    changed_by_id INTEGER   REFERENCES users(id),
    CHECK (exited_at IS NULL OR exited_at >= entered_at)
);

CREATE INDEX ix_stage_history_client_id ON client_stage_history(client_id);
CREATE INDEX ix_stage_history_stage_id  ON client_stage_history(stage_id);
-- Exactly one open (current) stage row per client.
CREATE UNIQUE INDEX ux_stage_history_open
    ON client_stage_history(client_id) WHERE exited_at IS NULL;

-- ---------- Milestones -------------------------------------------------------
-- 'overdue' is NOT a stored status: it is derived as
--   status <> 'done' AND due_date < CURRENT_DATE
-- so it can never go stale.
CREATE TABLE milestones (
    id           INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    client_id    INTEGER      NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
    title        VARCHAR(200) NOT NULL,
    due_date     DATE         NOT NULL,
    completed_at TIMESTAMP,
    owner_id     INTEGER      REFERENCES users(id),
    status       VARCHAR(20)  NOT NULL DEFAULT 'not_started'
                 CHECK (status IN ('not_started', 'in_progress', 'done')),
    created_at   TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    -- done <=> completed_at set
    CHECK ((status = 'done') = (completed_at IS NOT NULL))
);

CREATE INDEX ix_milestones_client_id ON milestones(client_id);
CREATE INDEX ix_milestones_owner_id  ON milestones(owner_id);
-- Open milestones ordered by due date: powers the "overdue" dashboard panel.
CREATE INDEX ix_milestones_open_due
    ON milestones(due_date) WHERE status <> 'done';

-- ---------- Blockers ---------------------------------------------------------
-- resolved_at IS NULL => open.
CREATE TABLE blockers (
    id           INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    client_id    INTEGER      NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
    milestone_id INTEGER      REFERENCES milestones(id) ON DELETE SET NULL,
    title        VARCHAR(200) NOT NULL,
    description  TEXT,
    severity     VARCHAR(10)  NOT NULL
                 CHECK (severity IN ('low', 'medium', 'high', 'critical')),
    owner_id     INTEGER      REFERENCES users(id),
    opened_at    TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    resolved_at  TIMESTAMP,
    external_ref VARCHAR(40),                -- e.g. 'IMPL-142' (JIRA / Redmine key)
    CHECK (resolved_at IS NULL OR resolved_at >= opened_at)
);

CREATE INDEX ix_blockers_client_id    ON blockers(client_id);
CREATE INDEX ix_blockers_milestone_id ON blockers(milestone_id);
CREATE INDEX ix_blockers_owner_id     ON blockers(owner_id);
-- Open blockers by severity + age: the hot path for the risk engine.
CREATE INDEX ix_blockers_open
    ON blockers(client_id, severity, opened_at) WHERE resolved_at IS NULL;

-- ---------- Activity log / notes ---------------------------------------------
CREATE TABLE notes (
    id         INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    client_id  INTEGER   NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
    author_id  INTEGER   REFERENCES users(id),
    body       TEXT      NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX ix_notes_client_created ON notes(client_id, created_at DESC);

-- ---------- Meetings (nice-to-have) ------------------------------------------
CREATE TABLE meetings (
    id           INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    client_id    INTEGER   NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
    held_at      TIMESTAMP NOT NULL,
    summary      TEXT,
    action_items TEXT,
    created_at   TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX ix_meetings_client_held ON meetings(client_id, held_at DESC);

-- Many-to-many: which team members attended which meeting.
CREATE TABLE meeting_attendees (
    meeting_id INTEGER NOT NULL REFERENCES meetings(id) ON DELETE CASCADE,
    user_id    INTEGER NOT NULL REFERENCES users(id)    ON DELETE CASCADE,
    PRIMARY KEY (meeting_id, user_id)
);

CREATE INDEX ix_meeting_attendees_user_id ON meeting_attendees(user_id);
