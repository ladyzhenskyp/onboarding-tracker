# Entity-Relationship Diagram

Source of truth for the DDL is [`db/schema.sql`](../db/schema.sql).
Design rationale is in [`schema-design.md`](schema-design.md).

```mermaid
erDiagram
    users ||--o{ clients : "owns (account owner)"
    users ||--o{ milestones : "owns"
    users ||--o{ blockers : "owns"
    users ||--o{ notes : "authors"
    users ||--o{ client_stage_history : "changed_by"
    users ||--o{ meeting_attendees : "attends"

    stages ||--o{ clients : "current_stage"
    stages ||--o{ client_stage_history : "stage"

    clients ||--o{ client_stage_history : "has visits"
    clients ||--o{ milestones : "has"
    clients ||--o{ blockers : "has"
    clients ||--o{ notes : "has"
    clients ||--o{ meetings : "has"

    milestones |o--o{ blockers : "optionally blocks"
    meetings ||--o{ meeting_attendees : "has"

    users {
        int id PK
        varchar name
        varchar email UK
        varchar role "csm | implementation_analyst | engineer | manager"
        boolean is_active
        timestamp created_at
    }

    stages {
        int id PK
        varchar key UK "kickoff | discovery | uat | prod | live"
        varchar name
        smallint sort_order UK
    }

    clients {
        int id PK
        varchar name UK
        varchar segment "enterprise | mid_market | smb"
        numeric contract_value
        date kickoff_date
        date target_go_live_date
        int owner_id FK
        int current_stage_id FK "denormalised from stage history"
        timestamp created_at
        timestamp updated_at
    }

    client_stage_history {
        int id PK
        int client_id FK
        int stage_id FK
        timestamp entered_at
        timestamp exited_at "NULL = current stage"
        int changed_by_id FK
    }

    milestones {
        int id PK
        int client_id FK
        varchar title
        date due_date
        timestamp completed_at
        int owner_id FK
        varchar status "not_started | in_progress | done (overdue is derived)"
        timestamp created_at
    }

    blockers {
        int id PK
        int client_id FK
        int milestone_id FK "nullable"
        varchar title
        text description
        varchar severity "low | medium | high | critical"
        int owner_id FK
        timestamp opened_at
        timestamp resolved_at "NULL = open"
        varchar external_ref "e.g. IMPL-142"
    }

    notes {
        int id PK
        int client_id FK
        int author_id FK
        text body
        timestamp created_at
    }

    meetings {
        int id PK
        int client_id FK
        timestamp held_at
        text summary
        text action_items
        timestamp created_at
    }

    meeting_attendees {
        int meeting_id PK,FK
        int user_id PK,FK
    }
```

## Derived (not stored) attributes

| Attribute                | Derived from                                                     |
|--------------------------|------------------------------------------------------------------|
| `client.health`          | Risk rules over open blockers, milestones, stage age, go-live date |
| `client.days_in_stage`   | `now() - client_stage_history.entered_at` where `exited_at IS NULL` |
| `milestone.is_overdue`   | `status <> 'done' AND due_date < today`                          |
| `blocker.is_open`        | `resolved_at IS NULL`                                            |
| `blocker.age_days`       | `now() - opened_at` (open blockers only)                         |
