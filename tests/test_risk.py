"""Unit tests for the risk engine — the cases listed in docs/risk-rules.md §5."""

from pathlib import Path

import pytest

from app.services.risk import ClientSnapshot, OpenBlocker, RiskConfig, evaluate


def snap(**overrides) -> ClientSnapshot:
    """A healthy client by default; override the fields the case cares about."""
    base = dict(
        current_stage_key="kickoff",
        current_stage_name="Kickoff",
        days_in_stage=3,
        days_to_go_live=60,
        open_blockers=(),
        overdue_milestones=0,
    )
    base.update(overrides)
    return ClientSnapshot(**base)


def rule_ids(result) -> list[str]:
    return [h.rule_id for h in result.reasons]


# --- baseline ----------------------------------------------------------------
def test_healthy_client_is_green_with_no_reasons():
    r = evaluate(snap())
    assert r.colour == "green"
    assert r.reasons == ()
    assert not r.is_at_risk


# --- blockers ------------------------------------------------------------------
def test_open_critical_blocker_is_red():
    r = evaluate(snap(open_blockers=(OpenBlocker("SSO broken", "critical", 1, "IMPL-142"),)))
    assert r.colour == "red"
    assert rule_ids(r) == ["critical_blocker"]
    assert "IMPL-142" in r.reasons[0].message


def test_high_blocker_at_exactly_threshold_is_green():
    r = evaluate(snap(open_blockers=(OpenBlocker("API keys", "high", 7),)))
    assert r.colour == "green"


def test_high_blocker_past_threshold_is_red():
    r = evaluate(snap(open_blockers=(OpenBlocker("API keys", "high", 8),)))
    assert r.colour == "red"
    assert rule_ids(r) == ["stale_high_blocker"]


def test_resolved_blockers_are_not_passed_in_and_medium_is_ignored():
    # Resolved blockers never reach the snapshot; a medium one never fires a rule.
    r = evaluate(snap(open_blockers=(OpenBlocker("Typo in report", "medium", 40),)))
    assert r.colour == "green"


# --- milestones ---------------------------------------------------------------
def test_two_overdue_milestones_is_amber():
    r = evaluate(snap(overdue_milestones=2))
    assert r.colour == "amber"
    assert rule_ids(r) == ["overdue_milestones"]


def test_one_overdue_milestone_is_green():
    assert evaluate(snap(overdue_milestones=1)).colour == "green"


# --- go-live ------------------------------------------------------------------
def test_go_live_in_14_days_in_uat_is_amber():
    r = evaluate(snap(current_stage_key="uat", current_stage_name="UAT", days_to_go_live=14))
    assert r.colour == "amber"
    assert rule_ids(r) == ["go_live_approaching"]


def test_go_live_in_14_days_in_prod_is_green():
    r = evaluate(snap(current_stage_key="prod", current_stage_name="Prod", days_to_go_live=14))
    assert r.colour == "green"


def test_go_live_missed_in_uat_is_red():
    r = evaluate(snap(current_stage_key="uat", current_stage_name="UAT", days_to_go_live=-3))
    assert r.colour == "red"
    assert rule_ids(r) == ["go_live_missed"]
    assert "3 days ago" in r.reasons[0].message


# --- time in stage --------------------------------------------------------------
def test_22_days_in_uat_is_amber():
    r = evaluate(snap(current_stage_key="uat", current_stage_name="UAT", days_in_stage=22))
    assert r.colour == "amber"
    assert rule_ids(r) == ["stage_overdue"]


def test_live_clients_are_never_flagged_for_stage_age():
    r = evaluate(snap(current_stage_key="live", current_stage_name="Live", days_in_stage=100))
    assert r.colour == "green"


# --- combinations & config -------------------------------------------------------
def test_multiple_rules_all_reported_and_worst_colour_wins():
    r = evaluate(
        snap(
            current_stage_key="uat",
            current_stage_name="UAT",
            days_in_stage=22,
            open_blockers=(OpenBlocker("Data feed down", "critical", 2),),
        )
    )
    assert r.colour == "red"
    assert set(rule_ids(r)) == {"critical_blocker", "stage_overdue"}


def test_config_override_raises_uat_threshold():
    cfg = RiskConfig(stage_max_days={"uat": 30})
    r = evaluate(snap(current_stage_key="uat", current_stage_name="UAT", days_in_stage=22), cfg)
    assert r.colour == "green"


def test_yaml_config_loads_and_matches_defaults():
    cfg = RiskConfig.from_yaml(Path(__file__).resolve().parent.parent / "app" / "risk_rules.yaml")
    assert cfg == RiskConfig()


def test_yaml_with_unknown_stage_fails_fast(tmp_path: Path):
    bad = tmp_path / "rules.yaml"
    bad.write_text("stage_max_days:\n  onboarding: 5\n")
    with pytest.raises(ValueError, match="unknown stage keys"):
        RiskConfig.from_yaml(bad)
