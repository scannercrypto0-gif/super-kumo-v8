"""Promotion delta tests. Every trust root is generated for the test only."""
from decimal import Decimal

import pytest

from aql.paper_sim.engine import PaperSimulator
from aql.promotion import EXITS, GATES, Lifecycle, _assess as assess, assess_factory, dashboard, live_candidate, seal
from tests.paper_sim.test_engine import arm, candle, watch


def documents(grade="SYNTHETIC_TESTED", verdict="SCIENTIFIC_PASS"):
    binding = dict(strategy_id="fixture", strategy_version="v1", category="spot", shadow_id="shadow",
                   code_sha256="d"*64, config_sha256="c"*64, protocol_sha256="a"*64, costs_sha256="b"*64)
    result = seal(dict(schema="aql.factory.promotion-result.v1", **binding, grade=grade, verdict=verdict,
                       blockers=[], attempts_sha256="e"*64,
                       scenarios={method: dict(status="MEASURED", reason=None, receipt_sha256="f"*64)
                                  if method == EXITS[0] else dict(status="N/A", reason="preregistered exclusion",
                                                                receipt_sha256=None) for method in EXITS}))
    policy = seal(dict(schema="aql.promotion.protocol.v1", **binding, shadow_until_ms=120000,
                       source_max_age_ms=1000, applicability={method: method == EXITS[0] for method in EXITS},
                       exclusions={method: "preregistered exclusion" for method in EXITS[1:]}))
    evidence = {gate: seal(dict(schema="aql.promotion.gate.v1", gate=gate, result_sha256=result["sha256"],
                                policy_sha256=policy["sha256"], status="PASS", valid_from_ms=0,
                                expires_ms=120000)) for gate in GATES}
    return result, dict(factory_pin=result["sha256"], policy=policy, policy_pin=policy["sha256"],
                        evidence=evidence, evidence_pins={gate: value["sha256"] for gate, value in evidence.items()},
                        at_ms=60000)


def eligible():
    # Exercises the positive policy logic with invented trust roots. No evidence is attested.
    result, args = documents("ORIGINAL_PIT_OOS")
    return assess(result, **args)


def cmd(op, at_ms, proof=None):
    return dict(op=op, at_ms=at_ms, proof=proof)


def test_fixture_science_does_not_promote_or_activate(tmp_path):
    result, args = documents()
    decision = assess(result, **args)
    assert (decision["scientific"], decision["promotion"], decision["paper"], decision["shadow"]) == (
        "SCIENTIFIC_PASS", "PROMOTION_BLOCKED", "PAPER_BLOCKED", "OBSERVATION_ONLY")
    manager = Lifecycle(tmp_path/"manager.jsonl", decision, assessment_pin=decision["sha256"])
    with pytest.raises(ValueError, match="ACTIVATION_DENIED"):
        manager.apply("activate", cmd("simulate_activation", 60000, "DISPOSABLE_TEST_ONLY"))
    assert not (tmp_path/"manager.jsonl").exists()


def test_forged_receipt_expired_gate_and_paper_gate_separation():
    result, args = documents("ORIGINAL_PIT_OOS")
    with pytest.raises(ValueError, match="PROMOTION_PIN"):
        assess(dict(result, category="changed"), **args)
    del args["evidence"]["paper_operations"]
    state = assess(result, **args)
    assert state["promotion"] == "PROMOTION_PASS" and state["paper"] == "PAPER_BLOCKED"
    args["at_ms"] = 120000
    state = assess(result, **args)
    assert state["promotion"] == "PROMOTION_BLOCKED" and state["shadow"] == "INACTIVE"


def test_durable_pause_retire_and_no_external_activation(tmp_path):
    state = eligible()
    pin = state["sha256"]
    path = tmp_path/"lifecycle.jsonl"
    approval = seal(dict(schema="aql.promotion.owner-decision.v1", assessment_sha256=pin, operation="retire",
                         valid_from_ms=62000, expires_ms=70000))
    manager = Lifecycle(path, state, assessment_pin=pin)
    activation = cmd("simulate_activation", 60000, "DISPOSABLE_TEST_ONLY")
    assert manager.apply("a", activation)["status"] == "PAPER_ACTIVE_FIXTURE"
    for operation in ("live", "telegram"):
        with pytest.raises(ValueError, match="ACTION_DENIED"):
            manager.apply(operation, cmd(operation, 61000))
    with pytest.raises(ValueError, match="OWNER_APPROVAL_REQUIRED"):
        manager.apply("r", cmd("retire", 63000, approval))
    pause = cmd("safety_pause", 62000, {"source_at_ms":60000, "source_valid":True})
    assert manager.apply("p", pause)["status"] == "TECHNICAL_PAUSE"
    restored = Lifecycle(path, state, assessment_pin=pin, owner_pins=[approval["sha256"]])
    assert restored.apply("p", pause) == manager.state
    assert restored.state["uptime_ms"] == 2000 and restored.state["alert"]
    assert restored.apply("r", cmd("retire", 63000, approval))["status"] == "RETIRED"
    assert Lifecycle(path, state, assessment_pin=pin, owner_pins=[approval["sha256"]]).state == restored.state


def test_dashboard_native_journal_restart_and_cost_once(tmp_path):
    state = eligible()
    pin = state["sha256"]
    manager = Lifecycle(tmp_path/"manager", state, assessment_pin=pin)
    manager.apply("a", cmd("simulate_activation", 60000, "DISPOSABLE_TEST_ONLY"))
    path = tmp_path/"sim"
    sim = PaperSimulator(path)
    first = watch(instance=pin)
    key = sim.identity(first)
    commands = [first, arm(), candle(), candle(180000, high="112", low="99", close="111")]
    for i, command in enumerate(commands):
        sim.apply(key, str(i), command)
    original = path.read_bytes()
    sim.apply(key, "3", commands[3])
    assert path.read_bytes() == original
    result = dashboard(manager, sim, as_of_ms=240000, source_at_ms=239999)
    assert result == dashboard(manager, PaperSimulator(path), as_of_ms=240000, source_at_ms=239999)
    trade = result["trades"][0]
    assert Decimal(trade["gross"]) - Decimal(trade["fees"]) - Decimal(trade["adverse"]) == Decimal(trade["net"])
    assert result["closed_trades"] == 1 and result["uptime_ms"] == 180000
    assert Decimal(result["mean_closed_trades_per_active_day"]) == 480
    assert result["actual_execution"] == "NONE" and result["freshness"] == "FRESH"


def test_live_candidate_one_exit_bound_to_risk_cost_and_version():
    state = eligible()
    args = dict(assessment_pin=state["sha256"], strategy_version="v1", risk_sha256=state["risk_sha256"],
                costs_sha256=state["costs_sha256"])
    candidate = live_candidate(state, EXITS[0], **args)
    assert candidate["exit_method"] == EXITS[0] and candidate["authority"] == "NONE"
    for selection in (EXITS[1], EXITS[:2]):
        with pytest.raises(ValueError, match="LIVE_CANDIDATE_EVIDENCE"):
            live_candidate(state, selection, **args)
    with pytest.raises(ValueError, match="LIVE_CANDIDATE_EVIDENCE"):
        live_candidate(state, EXITS[0], **dict(args, costs_sha256="0"*64))


def test_wire_handoff_sample_reseal_and_authority_denied():
    normalized, args = documents()
    policy = dict(args["policy"])
    del policy["sha256"]
    policy["strategy_version"] = "1"
    policy = seal(policy)
    strategy = dict(id=normalized["strategy_id"], version=1, code_sha256=normalized["code_sha256"],
                    parameters_sha256=normalized["config_sha256"])
    receipt = seal(dict(schema="aql.factory.shadow-promotion-handoff.v1", experiment_id="shadow",
                        baseline={**strategy, "id":"baseline"}, shadow=strategy, category=normalized["category"],
                        protocol_sha256=normalized["protocol_sha256"], evidence_grade="TEST_ONLY",
                        costs_sha256=normalized["costs_sha256"],
                        exit_families={method: dict(applicable=value["status"] == "MEASURED",
                                                    reason=value["reason"], results_sha256=value["receipt_sha256"])
                                       for method, value in normalized["scenarios"].items()},
                        factory_verdict="BLOCKED", research_state="BOUNDED_OBSERVATION",
                        blockers=["REAL_PIT_OOS_NOT_ATTESTED"],
                        receipts=dict(dossier_sha256="1"*64, admission_sha256="2"*64, evaluation_sha256="3"*64),
                        eligibility=dict(paper="PAPER_BLOCKED", live="NOT_AUTHORIZED", selected_live_exit=None)))
    options = dict(factory_pin=receipt["sha256"], policy=policy, policy_pin=policy["sha256"],
                   evidence={}, evidence_pins={}, at_ms=60000)
    accepted = assess_factory(receipt, **options)
    assert accepted["factory_sha256"] == receipt["sha256"] and accepted["paper"] == "PAPER_BLOCKED"
    for field, value in (("evidence_grade", "ORIGINAL_PIT_OOS"), ("eligibility", {"paper":"PAPER_ACTIVE"})):
        forged = seal({**{k:v for k,v in receipt.items() if k != "sha256"}, field:value})
        with pytest.raises(ValueError, match="PROMOTION_PIN"):
            assess_factory(forged, **options)
        with pytest.raises(ValueError, match="FACTORY_(GRADE|AUTHORITY)"):
            assess_factory(forged, **dict(options, factory_pin=forged["sha256"]))


def test_dashboard_preserves_unknown_and_partial_fills(tmp_path):
    state = eligible()
    pin = state["sha256"]
    manager = Lifecycle(tmp_path/"manager", state, assessment_pin=pin)
    manager.apply("a", cmd("simulate_activation", 60000, "DISPOSABLE_TEST_ONLY"))
    sim = PaperSimulator(tmp_path/"sim")
    for ident, low in (("a", "94"), ("f", "98")):
        first = watch(instance=pin, signal_id=ident*64)
        key = sim.identity(first)
        for i, command in enumerate((first, arm(), candle(low=low, high="111" if ident=="a" else "102",
                                                         taker_qty=".4"))):
            sim.apply(key, str(i), command)
    report = dashboard(manager, sim, as_of_ms=180000)
    assert {trade["phase"] for trade in report["trades"]} == {"UNKNOWN", "TRIGGERED"}
    assert all(trade["net"] is None and trade["fills"][0]["qty"] == "0.4" for trade in report["trades"])
    assert report["realized_net"] is None and report["freshness"] == "UNKNOWN"
