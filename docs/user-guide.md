# User guide

Who this is for: a customer-success / implementation team running several
client onboardings at once. The app answers three questions quickly —
*where is every account, which ones are in trouble, and why* — and gives the
team one place to record what happened.

## The pipeline

Every client moves through five fixed stages:

| Stage | What it means | Typical exit |
|---|---|---|
| **Kickoff** | Contract signed, kickoff call held, stakeholders mapped | Project charter signed |
| **Discovery / Configuration** | Requirements gathered, data mapped, SSO and integrations configured | Configuration spec approved |
| **UAT** | Client tests in a sandbox against their own data | Client signs off UAT |
| **Prod** | Production credentials issued, cutover rehearsed, go-live | Go-live date reached |
| **Live** | Hypercare, then steady state | — |

A client is always in exactly one stage. Moving backwards (Prod → UAT after a
failed release) is allowed and recorded.

## Health: red, amber, green

Health is **calculated every time a page loads** from the client's blockers,
milestones, stage and go-live date. Nobody sets it by hand, and the reasons
are always shown next to the colour.

| Colour | Fires when | Thresholds live in |
|---|---|---|
| **Red** | An open *critical* blocker · an open *high* blocker older than 7 days · the go-live date has passed and the client is not in Prod/Live | `app/risk_rules.yaml` |
| **Amber** | 2+ overdue milestones · go-live within 14 days and not in Prod/Live · longer in the current stage than its limit (Kickoff 10d, Discovery 30d, UAT 21d, Prod 14d) | |
| **Green** | None of the above | |

A client can trip several rules at once; all of them are listed. Live clients
are never flagged for stage age or go-live proximity, but a critical blocker
still turns them red.

## Pages

**Dashboard** (`/`) — the triage view: what needs a human today. Four tiles
(accounts, red, amber, green — click one to open the pipeline filtered to that
colour), the at-risk list with reasons and a days-in-stage bar against each
stage's limit, and a "This week" strip with the three nearest go-lives and the
three oldest open blockers. Charts and aggregate tables live on Insights.

**Insights** (`/insights`) — the analytical view. Filter by owner, segment,
current stage and kickoff date range (the filters are in the URL, so a view can
be shared as a link); three charts (accounts by stage, health mix, average days
in stage vs. limit), time-in-stage table, overdue milestones and oldest open
blockers, all computed over the same filtered set of accounts.

**Search** — the box in the header finds clients by name and blockers by
ticket ref or title as you type. Press `/` anywhere to focus it, arrow keys to
move, Enter to open the top result.

**Pipeline** (`/pipeline`) — one column per stage. The strip on top shows the
count and health mix per stage; each card shows the account, days in stage,
owner and — when at risk — the leading reason. Use the All / Red / Amber / Green
filter to see only what needs attention. Hover a card for full detail; click to
open the client.

**Clients** (`/clients`) — every account in one sortable table.

**Client page** (`/clients/{id}`) — the account's tearsheet: health and reasons,
stage timeline with days per stage, milestones, blockers (open and resolved),
notes and activity, meetings. All actions happen here (see below) and update
the page in place.

**Blockers** (`/blockers`) — every blocker across accounts, filterable by
open/closed, severity, owner and client. This is the list a manager scans
before the weekly review.

**Team** (`/team`) — accounts per owner with their red/amber/green split, how
many are still onboarding, how many carry a high or critical blocker, and total
contract value. Below it, each owner's accounts.

## Working an account

From the client page:

| Action | What it does |
|---|---|
| **Advance to …** | Moves the client to the next stage. Closes the current stage-history row, opens a new one, and adds a note to the activity log. |
| **Move** (with a reason) | Moves to any stage, forward or back. The reason is recorded in the note. |
| **Add blocker** | Title, severity, optional ticket reference (e.g. `IMPL-142` in JIRA/Redmine), owner and description. Opens immediately and feeds the health rules. |
| **Resolve** | Closes a blocker (records the timestamp). Resolved blockers stay visible, struck through. |
| **Add milestone** | Title, due date, optional owner. A milestone becomes *Overdue* automatically once its due date passes. |
| **Mark done** | Completes a milestone. |
| **Add note** | Free-text log entry, e.g. "Biweekly sync 9/8: client still needs to provide SSO metadata." |

Nothing is gated: you can advance a client with open blockers. The next page
load will show it red or amber with the reason, which is the point — the tool
records reality and makes the risk visible rather than blocking the workflow.

## Tables

Every table can be sorted by clicking a column heading (click again to
reverse). Text sorts alphabetically, numbers and dates by value, health and
severity by seriousness.

## Exports

The `Export ▾` menu in the header downloads Excel-ready CSV files: the pipeline export includes each
account's health colour and reasons; the blockers export includes age in days
and open/closed status.

## Demo data

The deployed demo is seeded with 20 fictional fintech/SaaS accounts and a
six-person team, designed to land on a realistic mix of red, amber and green.
All dates are relative to today, so the demo never looks stale. Names are
invented; any resemblance to real companies is coincidental.
