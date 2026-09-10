# At-risk rules specification

Health status is **computed, never stored**. This document is the contract
that `app/services/risk.py` (Phase 1) implements and `tests/test_risk.py`
verifies. Thresholds live in `app/risk_rules.yaml` so they can be tuned
without a code change.

## 1. Inputs

For a single client, evaluated "as of" a timestamp `now` (injected, so tests
are deterministic):

| Input                 | Source                                                             |
|-----------------------|--------------------------------------------------------------------|
| `current_stage_key`   | `stages.key` via `clients.current_stage_id`                        |
| `days_in_stage`       | `now - client_stage_history.entered_at` where `exited_at IS NULL`  |
| `days_to_go_live`     | `clients.target_go_live_date - now.date()` (negative = past due)   |
| `open_blockers[]`     | rows in `blockers` where `resolved_at IS NULL`: `severity`, `age_days = now - opened_at` |
| `overdue_milestones`  | count of `milestones` where `status <> 'done' AND due_date < now.date()` |

## 2. Rules

Rules are evaluated **in order**; a client's colour is the **worst** colour
of any rule that fires (Red > Amber > Green). Every rule that fires is
recorded, so the UI can show *all* reasons, not just the first.

| # | Rule id                 | Condition                                                             | Colour | Reason text (template)                                  |
|---|-------------------------|-----------------------------------------------------------------------|--------|---------------------------------------------------------|
| 1 | `critical_blocker`      | any open blocker with `severity = critical`                           | Red    | "Open critical blocker: {title} ({external_ref})"       |
| 2 | `stale_high_blocker`    | any open blocker with `severity = high` and `age_days > high_blocker_max_age_days` (7) | Red | "High blocker open {age} days: {title}"          |
| 3 | `overdue_milestones`    | `overdue_milestones >= overdue_milestone_threshold` (2)               | Amber  | "{n} overdue milestones"                                |
| 4 | `go_live_approaching`   | `0 <= days_to_go_live <= go_live_warning_days` (14) and stage not in `go_live_safe_stages` (prod, live) | Amber | "Go-live in {days} days but still in {stage}" |
| 5 | `go_live_missed`        | `days_to_go_live < 0` and stage not in `go_live_safe_stages`          | Red    | "Go-live date passed {days} days ago; still in {stage}" |
| 6 | `stage_overdue`         | `days_in_stage > stage_max_days[current_stage_key]`                   | Amber  | "{days} days in {stage} (threshold {max})"              |
| — | (none fired)            |                                                                       | Green  | "On track"                                              |

Rule 5 is an addition to the original brief: a go-live date that has
already passed while the client is still in UAT is worse than one that is
merely approaching, and CS managers will expect it to be red.

Clients in the `live` stage skip rules 4–6 (they are done onboarding) but
rules 1–3 still apply — a live client can still have a critical blocker.

## 3. Output

```python
@dataclass(frozen=True)
class HealthResult:
    colour: Literal["red", "amber", "green"]
    reasons: list[RuleHit]          # empty when green

@dataclass(frozen=True)
class RuleHit:
    rule_id: str                    # e.g. "stale_high_blocker"
    colour: Literal["red", "amber"]
    message: str                    # rendered reason text
```

The dashboard's "at-risk accounts" list is every client whose colour is not
green, sorted red first, then by `days_to_go_live` ascending.

## 4. Configuration (`app/risk_rules.yaml`)

```yaml
# Thresholds for the risk engine. See docs/risk-rules.md.
high_blocker_max_age_days: 7
overdue_milestone_threshold: 2
go_live_warning_days: 14
go_live_safe_stages: [prod, live]
stage_max_days:
  kickoff: 10
  discovery: 30
  uat: 21
  prod: 14
  live: null        # never flagged for stage age
```

Loading rules: read once at startup into a frozen `RiskConfig` dataclass;
missing keys fall back to the defaults above; unknown stage keys raise at
startup (fail fast rather than silently never flagging a stage).

## 5. Test cases (to be written in `tests/test_risk.py`)

| Case                                                           | Expected                                  |
|----------------------------------------------------------------|-------------------------------------------|
| No blockers, no milestones, 3 days in kickoff, go-live in 60d  | green, no reasons                         |
| One open critical blocker                                      | red, `critical_blocker`                   |
| One open high blocker aged 7 days exactly                      | green (threshold is strictly greater)     |
| One open high blocker aged 8 days                              | red, `stale_high_blocker`                 |
| One resolved critical blocker                                  | green                                     |
| 2 overdue milestones                                           | amber, `overdue_milestones`               |
| 1 overdue milestone                                            | green                                     |
| Go-live in 14 days, stage = uat                                | amber, `go_live_approaching`              |
| Go-live in 14 days, stage = prod                               | green                                     |
| Go-live 3 days ago, stage = uat                                | red, `go_live_missed`                     |
| 22 days in uat                                                 | amber, `stage_overdue`                    |
| 100 days in live                                               | green                                     |
| Critical blocker **and** 22 days in uat                        | red with **two** reasons                  |
| Config overrides `uat: 30`, 22 days in uat                     | green                                     |

## 6. Why these rules (interview framing)

They mirror how CS/implementation teams actually triage:

- **Critical / stale-high blockers** — the equivalent of a P1 ticket sitting
  in JIRA untouched for a week; that is the first thing a manager asks about.
- **Overdue milestones** — one slipped deliverable is noise; two is a pattern.
- **Go-live proximity** — the client has told their business a date; if we
  are not in Prod two weeks out, the date is at risk regardless of blockers.
- **Time in stage** — UAT that drags past three weeks almost always means the
  client is not testing, which is a relationship problem, not a technical one.
