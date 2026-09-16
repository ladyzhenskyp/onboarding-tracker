"""Rule-based health engine.

Implements docs/risk-rules.md. Pure functions over a `ClientSnapshot`, so the
rules can be unit-tested with no database; `snapshot_from_client` builds a
snapshot from ORM objects for the app.

    result = evaluate(snapshot, config)
    result.colour   -> "red" | "amber" | "green"
    result.reasons  -> [RuleHit(rule_id, colour, message), ...]  (all rules that fired)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Literal

import yaml

if TYPE_CHECKING:
    from app.models import Client

Colour = Literal["red", "amber", "green"]
_RANK: dict[str, int] = {"green": 0, "amber": 1, "red": 2}


# --------------------------------------------------------------------------- config
@dataclass(frozen=True)
class RiskConfig:
    high_blocker_max_age_days: int = 7
    overdue_milestone_threshold: int = 2
    go_live_warning_days: int = 14
    go_live_safe_stages: frozenset[str] = frozenset({"prod", "live"})
    stage_max_days: dict[str, int | None] = field(
        default_factory=lambda: {
            "kickoff": 10,
            "discovery": 30,
            "uat": 21,
            "prod": 14,
            "live": None,
        }
    )

    @classmethod
    def from_yaml(cls, path: Path) -> RiskConfig:
        """Load thresholds; missing keys fall back to the defaults above."""
        raw = yaml.safe_load(path.read_text()) or {}
        defaults = cls()
        stage_max = dict(defaults.stage_max_days)
        stage_max.update(raw.get("stage_max_days") or {})
        unknown = set(stage_max) - set(defaults.stage_max_days)
        if unknown:  # fail fast rather than silently never flagging a stage
            raise ValueError(f"risk_rules.yaml: unknown stage keys {sorted(unknown)}")
        return cls(
            high_blocker_max_age_days=int(
                raw.get("high_blocker_max_age_days", defaults.high_blocker_max_age_days)
            ),
            overdue_milestone_threshold=int(
                raw.get("overdue_milestone_threshold", defaults.overdue_milestone_threshold)
            ),
            go_live_warning_days=int(
                raw.get("go_live_warning_days", defaults.go_live_warning_days)
            ),
            go_live_safe_stages=frozenset(
                raw.get("go_live_safe_stages", sorted(defaults.go_live_safe_stages))
            ),
            stage_max_days=stage_max,
        )


# --------------------------------------------------------------------------- inputs
@dataclass(frozen=True)
class OpenBlocker:
    title: str
    severity: str  # low | medium | high | critical
    age_days: int
    external_ref: str | None = None


@dataclass(frozen=True)
class ClientSnapshot:
    """Everything the rules need about one client, as of `now`."""

    current_stage_key: str
    current_stage_name: str
    days_in_stage: int
    days_to_go_live: int  # negative = go-live date already passed
    open_blockers: tuple[OpenBlocker, ...] = ()
    overdue_milestones: int = 0


# --------------------------------------------------------------------------- outputs
@dataclass(frozen=True)
class RuleHit:
    rule_id: str
    colour: Literal["red", "amber"]
    message: str


@dataclass(frozen=True)
class HealthResult:
    colour: Colour
    reasons: tuple[RuleHit, ...] = ()

    @property
    def is_at_risk(self) -> bool:
        return self.colour != "green"


# --------------------------------------------------------------------------- rules
def evaluate(s: ClientSnapshot, cfg: RiskConfig | None = None) -> HealthResult:
    cfg = cfg or RiskConfig()
    hits: list[RuleHit] = []

    # 1. any open critical blocker -> red
    for b in s.open_blockers:
        if b.severity == "critical":
            ref = f" ({b.external_ref})" if b.external_ref else ""
            hits.append(
                RuleHit("critical_blocker", "red", f"Open critical blocker: {b.title}{ref}")
            )

    # 2. any open high blocker older than threshold -> red
    for b in s.open_blockers:
        if b.severity == "high" and b.age_days > cfg.high_blocker_max_age_days:
            hits.append(
                RuleHit(
                    "stale_high_blocker",
                    "red",
                    f"High blocker open {b.age_days} days: {b.title}",
                )
            )

    # 3. overdue milestones at/above threshold -> amber
    if s.overdue_milestones >= cfg.overdue_milestone_threshold:
        hits.append(
            RuleHit("overdue_milestones", "amber", f"{s.overdue_milestones} overdue milestones")
        )

    in_safe_stage = s.current_stage_key in cfg.go_live_safe_stages

    # 4. go-live approaching while not in prod/live -> amber
    if not in_safe_stage and 0 <= s.days_to_go_live <= cfg.go_live_warning_days:
        hits.append(
            RuleHit(
                "go_live_approaching",
                "amber",
                f"Go-live in {s.days_to_go_live} days but still in {s.current_stage_name}",
            )
        )

    # 5. go-live already missed while not in prod/live -> red
    if not in_safe_stage and s.days_to_go_live < 0:
        hits.append(
            RuleHit(
                "go_live_missed",
                "red",
                f"Go-live date passed {-s.days_to_go_live} days ago; "
                f"still in {s.current_stage_name}",
            )
        )

    # 6. too long in current stage -> amber
    max_days = cfg.stage_max_days.get(s.current_stage_key)
    if max_days is not None and s.days_in_stage > max_days:
        hits.append(
            RuleHit(
                "stage_overdue",
                "amber",
                f"{s.days_in_stage} days in {s.current_stage_name} (threshold {max_days})",
            )
        )

    colour: Colour = "green"
    for h in hits:
        if _RANK[h.colour] > _RANK[colour]:
            colour = h.colour
    return HealthResult(colour=colour, reasons=tuple(hits))


# --------------------------------------------------------------------------- ORM bridge
def snapshot_from_client(client: Client, now: datetime) -> ClientSnapshot:
    """Build a snapshot from a loaded Client (with stage_history, blockers, milestones)."""
    today: date = now.date()
    open_row = next((h for h in client.stage_history if h.exited_at is None), None)
    entered = open_row.entered_at if open_row else client.created_at
    return ClientSnapshot(
        current_stage_key=client.current_stage.key,
        current_stage_name=client.current_stage.name,
        days_in_stage=(now - entered).days,
        days_to_go_live=(client.target_go_live_date - today).days,
        open_blockers=tuple(
            OpenBlocker(b.title, b.severity, b.age_days(now), b.external_ref)
            for b in client.blockers
            if b.is_open
        ),
        overdue_milestones=sum(1 for m in client.milestones if m.is_overdue(today)),
    )


def evaluate_client(client: Client, now: datetime, cfg: RiskConfig | None = None) -> HealthResult:
    return evaluate(snapshot_from_client(client, now), cfg)
