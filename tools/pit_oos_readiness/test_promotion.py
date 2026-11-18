import pytest

from research_wp_r0.frozen_research_plan import commit_research_plan
from research_wp_r0.strategy_definition import canonical
from tools.pit_oos_readiness import promotion as p


@pytest.fixture
def frozen():
    boundaries = [f"2026-11-{day:02}T00:00:00Z" for day in (1, 2, 5, 6, 9, 10)]
    split = {name: boundaries[index:index + 2] for index, name in enumerate(p.SPLITS)}
    strategy = "a" * 64
    window = dict(**split, venue="Binance Spot", symbol="BTCUSDT", interval="15m",
                  strategy_sha256=strategy, independent_attestation="SKIPPED_BY_OWNER",
                  holdout_access="SEALED_UNOPENED")
    source = dict(path_template=p.ARCHIVE, checksum_suffix=".CHECKSUM")
    protocol = dict(schema="aql.delayed-prospective-protocol.v1", window_sha256=p.sha(canonical(window)),
                    window=split, source=source, strategy_sha256=strategy,
                    selection={"stop": "fixed"}, cost_model={"mode": "fixture"},
                    metrics=["net"], baseline={"id": "fixed"},
                    independent_attestation="SKIPPED_BY_OWNER", collection="NOT_ACTIVATED")
    plan, pin = commit_research_plan(
        "fixture", [("sma3-12-v1", strategy)], protocol_digest=p.sha(canonical(protocol)),
        dataset_digest=p.sha(canonical(source)), split_digest=p.sha(canonical(split)),
        metrics=protocol["metrics"], selection_rule=protocol["selection"], cost_model=protocol["cost_model"],
        baseline_digest=p.sha(canonical(protocol["baseline"])),
    )
    return plan, canonical(protocol), canonical(window), pin


def test_valid_fixture_preflight_preserves_grade_and_excludes_holdout(frozen):
    result = p.review(p.verify_delayed_plan(*frozen), evidence_grade="SYNTHETIC_TESTED")
    assert result["evidence_grade"] == "SYNTHETIC_TESTED"
    assert result["independent_attestation"] == "SKIPPED_BY_OWNER"
    assert result["scientific_status"] == "REAL_PIT_OOS_BLOCKED"
    assert [item["date"] for item in result["planned_archives"]] == ["2026-11-01", "2026-11-05"]
    assert result["earliest_evaluation_utc_date"] == "2026-11-06"
    assert result["trading_authority"] == "NONE"


@pytest.mark.parametrize("index,reason", [(0, "commitment mismatch"),
    (1, "PROTOCOL_OR_WINDOW_PIN"), (2, "PROTOCOL_OR_WINDOW_PIN")])
def test_frozen_bytes_reject_mutation(frozen, index, reason):
    args = list(frozen)
    args[index] += b" "
    with pytest.raises(ValueError, match=reason):
        p.verify_delayed_plan(*args)


def test_holdout_and_independent_grade_override_rejected(frozen):
    checked = p.verify_delayed_plan(*frozen)
    with pytest.raises(ValueError, match="HOLDOUT_ACCESS_DENIED"):
        p.review(checked, holdout_requested=True)
    with pytest.raises(ValueError, match="EVIDENCE_GRADE_DENIED"):
        p.review(checked, evidence_grade="INDEPENDENTLY_VERIFIED")


def test_exploratory_results_cannot_activate_or_remove_strategy(frozen):
    result = p.review(p.verify_delayed_plan(*frozen), evidence_grade="EXPLORATORY")
    assert result["decisions"] == {
        "RESEARCH_REVIEW": "REPORT_ONLY",
        "RESEARCH_TO_SHADOW": "QUALIFICATION_AND_OWNER_AUTHORITY_REQUIRED",
        "SHADOW_TO_PAPER": "QUALIFICATION_AND_OWNER_AUTHORITY_REQUIRED",
        "PAPER_TO_LIVE": "SEPARATE_OWNER_AUTHORIZATION_NO_AUTO_PROMOTION",
        "REMOVE_PAPER": "OWNER_APPROVAL_REQUIRED",
    }
    assert result["lab"] == "NOT_AUTHORIZED" and result["scientific_status"] == "REAL_PIT_OOS_BLOCKED"
    for action in ("RESEARCH_TO_SHADOW", "SHADOW_TO_PAPER", "PAPER_TO_LIVE", "REMOVE_PAPER"):
        request = p.review(p.verify_delayed_plan(*frozen), evidence_grade="EXPLORATORY", action=action)
        assert request["request_disposition"] == result["decisions"][action]
        assert request["state_changed"] is False
