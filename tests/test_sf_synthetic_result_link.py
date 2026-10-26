"""SF-LEDGER-LINK-01: bounded synthetic evidence/Factory-ledger integration."""
import copy
import sqlite3

import pytest

from research_wp_r0.attempt_ledger import AttemptLedger
from research_wp_r0.frozen_attempt_writer import FrozenAttemptWriter
from research_wp_r0.sf_breakout_pilot import PilotPlan, SPEC, synthetic_fixture, run_pilot
from research_wp_r0.sf_synthetic_result_link import (
    FAMILY, VERSIONS, frozen_pilot_family, version_digest,
    read_synthetic_evidence, record_synthetic_result)
from research_wp_r0.strategy_definition import digest


def prepared(tmp_path):
    plan = PilotPlan(copy.deepcopy(SPEC))
    bars = synthetic_fixture()
    data_digest = digest(bars)
    raw_family, family_digest = frozen_pilot_family(
        plan=plan, expected_plan_digest=plan.digest,
        expected_data_digest=data_digest)
    db_path = tmp_path / "factory.sqlite"
    ledger = AttemptLedger(db_path)
    writer = FrozenAttemptWriter(ledger, raw_family, family_digest)
    for v in VERSIONS:
        writer.record_attempt({"state": "PENDING", "family_id": FAMILY,
                               "candidate_id": v, "input_digest": data_digest,
                               "strategy_digest": version_digest(v)})
    result = run_pilot(bars, plan=plan, expected_plan_digest=plan.digest,
                       expected_data_digest=data_digest)
    return db_path, ledger, writer, raw_family, family_digest, plan, bars, data_digest, result


def record(ctx, **kwargs):
    path, ledger, writer, raw, family_digest, plan, bars, data_digest, result = ctx
    args = {"raw_plan": raw, "expected_family_digest": family_digest,
            "plan": plan, "expected_plan_digest": plan.digest,
            "bars": bars, "expected_data_digest": data_digest, "result": result}
    args.update(kwargs)
    return record_synthetic_result(writer, **args)


def test_atomic_synthetic_only_receipt_and_idempotent_replay(tmp_path):
    ctx = prepared(tmp_path)
    before_events, before_head = ctx[1].snapshot()
    receipt, payload = record(ctx)
    receipt2, payload2 = record(ctx)
    assert (receipt, payload) == (receipt2, payload2)
    assert payload["status"] == "SYNTHETIC_INTEGRATION_RESULT_NOT_RESEARCH_COMPLETE"
    assert payload["pilot_result_digest"] == ctx[-1]["result_digest"]
    assert set(payload["version_digests"]) == {"BASE", "SHADOW"}
    assert payload["costs_digest"]
    assert payload["attempt_checkpoint"] == list(before_head)
    assert ctx[1].snapshot() == (before_events, before_head)
    records, evidence_head = read_synthetic_evidence(ctx[1], expected_evidence_checkpoint=receipt)
    assert evidence_head == receipt and len(records) == 1
    reopened = AttemptLedger(ctx[0], expected_checkpoint=before_head)
    assert read_synthetic_evidence(reopened, expected_evidence_checkpoint=receipt)[0] == records


def test_no_pending_version_never_appends_evidence(tmp_path):
    ctx = prepared(tmp_path)
    # Attempt events are append-only, terminal ABANDONED is not a successful run.
    ctx[2].record_attempt({"state": "ABANDONED", "family_id": FAMILY,
                           "candidate_id": "SHADOW", "input_digest": ctx[-2],
                           "strategy_digest": version_digest("SHADOW")})
    with pytest.raises(ValueError, match="pending"):
        record(ctx)
    assert read_synthetic_evidence(ctx[1])[0] == ()


def test_changed_data_or_plan_or_result_is_rejected(tmp_path):
    ctx = prepared(tmp_path)
    bad = copy.deepcopy(ctx[-1])
    bad["versions"]["BASE"]["events"].append({"index": 1, "kind": "FABRICATED"})
    with pytest.raises(ValueError, match="digest mismatch"):
        record(ctx, result=bad)
    bad_result = copy.deepcopy(ctx[-1])
    bad_result["versions"]["BASE"]["events"].append({"index": 1, "kind": "FABRICATED"})
    bad_result["result_digest"] = digest({k: v for k, v in bad_result.items() if k != "result_digest"})
    with pytest.raises(ValueError, match="replay/result mismatch"):
        record(ctx, result=bad_result)
    with pytest.raises(ValueError, match="Research plan commitment mismatch|family"):
        record(ctx, expected_family_digest="0"*64)
    with pytest.raises(ValueError, match="immutable synthetic family|fixture|data"):
        record(ctx, expected_data_digest="f"*64)
    assert read_synthetic_evidence(ctx[1])[0] == ()


def test_evidence_chain_detects_tamper_and_rollback_anchor(tmp_path):
    ctx = prepared(tmp_path)
    checkpoint, _ = record(ctx)
    with pytest.raises(ValueError, match="anchor"):
        read_synthetic_evidence(ctx[1], expected_evidence_checkpoint=(0, "0"*64))
    with sqlite3.connect(ctx[0]) as conn:
        conn.execute("UPDATE synthetic_result_evidence SET payload=? WHERE seq=1", (b'{}',))
    with pytest.raises(ValueError, match="Corrupt|mismatch"):
        read_synthetic_evidence(ctx[1], expected_evidence_checkpoint=checkpoint)


def test_missing_evidence_is_not_false_success(tmp_path):
    ctx = prepared(tmp_path)
    records, head = read_synthetic_evidence(ctx[1])
    assert records == () and head == (0, "0"*64)
    with pytest.raises(ValueError, match="missing"):
        read_synthetic_evidence(ctx[1], expected_evidence_checkpoint=(1, "a"*64))


def test_no_complete_and_no_core_transition_relabeling(tmp_path):
    ctx = prepared(tmp_path)
    receipt, details = record(ctx)
    states = [e["state"] for e in ctx[1].snapshot()[0]]
    assert states == ["PENDING", "PENDING"]
    assert "COMPLETE" not in states
    assert "READY" not in states
    assert details["oos"] == "NOT_OPENED" and details["paper"] == "NOT_STARTED"
    assert "WATCH" not in details["status"]


def test_reject_malformed_synthetic_lifecycle_payload(tmp_path):
    ctx = prepared(tmp_path)
    for k, v in (("paper", "RUNNING"), ("oos", "OPENED"), ("actual_fills", "VERIFIED")):
        bad = copy.deepcopy(ctx[-1])
        bad[k] = v
        with pytest.raises(ValueError, match="only|fills"):
            record(ctx, result=bad)
    assert read_synthetic_evidence(ctx[1])[0] == ()
