"""SF-DEC-21 B — synthetic-only integrated Factory acceptance."""
import copy
import json
import sqlite3

import pytest

from research_wp_r0.attempt_ledger import AttemptLedger
from research_wp_r0.sf_breakout_pilot import PilotPlan, SPEC, run_pilot, synthetic_fixture
from research_wp_r0.sf_synthetic_workflow import (
    pilot_commitments, run_workflow, verify_workflow, report_json, report_summary)
from research_wp_r0.strategy_definition import digest


def frozen():
    proposed = pilot_commitments()
    return {key: proposed[key] for key in
            ("pilot_plan_digest", "fixture_digest", "family_digest")}


def reopen(db, expected, result):
    return verify_workflow(
        db, expected=expected, expected_report_digest=result["report_digest"],
        expected_attempt_checkpoint=tuple(result["attempt_checkpoint"]),
        expected_evidence_checkpoint=tuple(result["evidence_checkpoint"]))


def test_complete_synthetic_path_and_reopen(tmp_path):
    db = tmp_path / "research.sqlite"
    expected = frozen()
    report = run_workflow(db, expected=expected)
    assert report == reopen(db, expected, report)
    assert report["status"] == "SYNTHETIC_INTEGRATION_ONLY_NOT_RESEARCH_COMPLETE"
    assert report["source"] == "SYNTHETIC_500_BARS"
    assert report["plan_kind"] == "PilotPlan_NOT_StrategyDefinition"
    assert report["attempt_states"] == {"BASE": "PENDING", "SHADOW": "PENDING"}
    assert set(report["versions"]) == {"BASE", "SHADOW"}
    assert set(report["cost_assumptions"]) == {"BASE_COST", "STRESS_COST"}
    assert report["independent_custody"] == "NOT_VERIFIED"
    assert report["oos"] == "NOT_OPENED" and report["paper"] == "NOT_STARTED"
    assert report["actual_fills"] == "NOT_OBSERVED"
    assert report["selection"] == "NONE" and report["promotion"] == "NONE"
    assert "SYNTHETIC" in report_summary(report)
    assert json.loads(report_json(report)) == report
    events, _ = AttemptLedger(db).snapshot()
    assert len(events) == 2 and all(e["state"] == "PENDING" for e in events)


def test_idempotent_and_byte_stable(tmp_path):
    db = tmp_path / "research.sqlite"
    expected = frozen()
    first = run_workflow(db, expected=expected)
    second = run_workflow(db, expected=expected)
    assert report_json(first) == report_json(second)
    assert first["evidence_checkpoint"] == second["evidence_checkpoint"]
    assert first["attempt_checkpoint"] == second["attempt_checkpoint"]


def test_wrong_predeclared_commitment_blocks_creation(tmp_path):
    db = tmp_path / "research.sqlite"
    expected = frozen()
    for field in expected:
        wrong = {**expected, field: "0" * 64}
        with pytest.raises(ValueError, match="commitments"):
            run_workflow(db, expected=wrong)
        assert not db.exists()


def test_retained_report_and_anchors_are_necessary(tmp_path):
    db = tmp_path / "research.sqlite"
    expected = frozen()
    report = run_workflow(db, expected=expected)
    with pytest.raises(ValueError, match="report digest"):
        verify_workflow(
            db, expected=expected, expected_report_digest="f"*64,
            expected_attempt_checkpoint=tuple(report["attempt_checkpoint"]),
            expected_evidence_checkpoint=tuple(report["evidence_checkpoint"]))
    with pytest.raises(ValueError, match="checkpoint|anchor"):
        verify_workflow(
            db, expected=expected, expected_report_digest=report["report_digest"],
            expected_attempt_checkpoint=(0, "0"*64),
            expected_evidence_checkpoint=tuple(report["evidence_checkpoint"]))
    with pytest.raises(ValueError, match="anchor|checkpoint"):
        verify_workflow(
            db, expected=expected, expected_report_digest=report["report_digest"],
            expected_attempt_checkpoint=tuple(report["attempt_checkpoint"]),
            expected_evidence_checkpoint=(0, "0"*64))


def test_report_tamper_cannot_match_retained_digest(tmp_path):
    db = tmp_path / "research.sqlite"
    report = run_workflow(db, expected=frozen())
    changed = copy.deepcopy(report)
    changed["paper"] = "RUNNING"
    with pytest.raises(ValueError, match="digest mismatch"):
        report_json(changed)
    changed["report_digest"] = digest({k: v for k, v in changed.items()
                                        if k != "report_digest"})
    with pytest.raises(ValueError, match="report digest"):
        verify_workflow(
            db, expected=frozen(), expected_report_digest=changed["report_digest"],
            expected_attempt_checkpoint=tuple(report["attempt_checkpoint"]),
            expected_evidence_checkpoint=tuple(report["evidence_checkpoint"]))


def test_missing_shadow_receipt_fails_closed(tmp_path):
    db = tmp_path / "research.sqlite"
    expected = frozen()
    report = run_workflow(db, expected=expected)
    with sqlite3.connect(db) as conn:
        conn.execute("DELETE FROM receipts WHERE seq=2")
    with pytest.raises(ValueError):
        reopen(db, expected, report)


def test_missing_db_is_not_success(tmp_path):
    db = tmp_path / "missing.sqlite"
    with pytest.raises(ValueError, match="Existing"):
        verify_workflow(
            db, expected=frozen(), expected_report_digest="a"*64,
            expected_attempt_checkpoint=(2, "a"*64),
            expected_evidence_checkpoint=(1, "a"*64))
    assert not db.exists()


def test_shadow_missing_volume_does_not_change_base():
    plan = PilotPlan(SPEC)
    bars = list(synthetic_fixture())
    original = run_pilot(bars, plan=plan, expected_plan_digest=plan.digest,
                         expected_data_digest=digest(bars))
    bars[24] = (*bars[24][:6], None)
    modified = run_pilot(bars, plan=plan, expected_plan_digest=plan.digest,
                         expected_data_digest=digest(bars))
    assert original["versions"]["BASE"] == modified["versions"]["BASE"]
    assert any(e["kind"] == "BLOCKED_MISSING_REQUIRED_DATA"
               for e in modified["versions"]["SHADOW"]["events"])
    assert modified["paper"] == "NOT_STARTED"
