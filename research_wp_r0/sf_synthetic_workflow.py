"""SF-DEC-21 B: synthetic-only Factory workflow and independently checkable report.

No genuine historical/OOS/PAPER work, general StrategyDefinition execution,
Core lifecycle, external anchor authority, or research COMPLETE state.
"""
from pathlib import Path
import json

from .attempt_ledger import AttemptLedger
from .frozen_attempt_writer import FrozenAttemptWriter
from .sf_breakout_pilot import PilotPlan, SPEC, COSTS, synthetic_fixture, run_pilot
from .sf_synthetic_result_link import (
    FAMILY, VERSIONS, frozen_pilot_family, record_synthetic_result,
    read_synthetic_evidence, version_digest,
)
from .strategy_definition import canonical, digest


def pilot_commitments():
    """Proposed pre-run commitments. Retain externally BEFORE authorizing run.

    Computing these locally does not demonstrate independent prior custody.
    """
    plan = PilotPlan(SPEC)
    fixture = synthetic_fixture()
    data_digest = digest(fixture)
    raw, family_digest = frozen_pilot_family(
        plan=plan, expected_plan_digest=plan.digest,
        expected_data_digest=data_digest)
    return {"pilot_plan_digest": plan.digest, "fixture_digest": data_digest,
            "family_digest": family_digest, "family_plan": raw}


def _verify_frozen(expected):
    if type(expected) is not dict or set(expected) != {
            "pilot_plan_digest", "fixture_digest", "family_digest"}:
        raise ValueError("Explicit three external expected commitments required")
    proposed = pilot_commitments()
    if any(proposed[k] != expected[k] for k in expected):
        raise ValueError("Expected pre-run commitments changed")
    return proposed


def _counts(version):
    events = version["events"]
    kinds = [e["kind"] for e in events]
    trades = version["trades"]
    open_position = version["open_position"]
    pending = version["pending_action"]
    return {"entry_signals": kinds.count("ENTRY_SIGNAL"),
            "exit_signals": kinds.count("EXIT_SIGNAL"),
            "simulated_entries": kinds.count("SIMULATED_ENTRY"),
            "simulated_exits": kinds.count("SIMULATED_EXIT"),
            "closed_trades": len(trades),
            "missing_required_data": kinds.count("BLOCKED_MISSING_REQUIRED_DATA"),
            "volume_veto": kinds.count("SHADOW_VOLUME_VETO"),
            "rejected_capital": kinds.count("REJECTED_CAPITAL"),
            "unresolved_boundary": sum(e.get("status") == "UNRESOLVED_BOUNDARY"
                                       for e in events),
            "terminal_open_position": open_position is not None,
            "terminal_pending_action": pending is not None}


def _report(result, evidence, evidence_checkpoint, attempt_checkpoint, expected):
    if len(evidence) != 1:
        raise ValueError("Exactly one synthetic research receipt required")
    e = evidence[0]
    if (e["pilot_result_digest"] != result["result_digest"]
            or e["family_digest"] != expected["family_digest"]
            or e["fixture_digest"] != expected["fixture_digest"]
            or e["pilot_plan_digest"] != expected["pilot_plan_digest"]
            or e["attempt_checkpoint"] != list(attempt_checkpoint)):
        raise ValueError("Result/evidence/attempt binding mismatch")
    summaries = {}
    for v in VERSIONS:
        item = result["versions"][v]
        if e["version_digests"][v] != version_digest(v):
            raise ValueError("Version identity mismatch")
        if e["version_result_digests"][v] != digest(item):
            raise ValueError("Version evidence mismatch")
        summaries[v] = {"version_id": item["version"], "strategy_digest": version_digest(v),
                        "version_result_digest": digest(item),
                        "counts": _counts(item),
                        "accounting": {
                            cost: {"closed_trades": len(item["accounting"][cost]["trades"]),
                                   "realized_pnl_quote": item["accounting"][cost]["realized_pnl_quote"],
                                   "terminal_equity_quote": item["accounting"][cost]["terminal_equity_quote"],
                                   "open_position_mark_quote": item["accounting"][cost]["open_position_mark_quote"],
                                   "open_position_unrealized":
                                       item["accounting"][cost]["open_position_unrealized"]}
                            for cost in ("BASE_COST", "STRESS_COST")}}
    report = {"schema": "sf-synthetic-workflow-report-1",
              "status": "SYNTHETIC_INTEGRATION_ONLY_NOT_RESEARCH_COMPLETE",
              "source": "SYNTHETIC_500_BARS", "plan_kind": "PilotPlan_NOT_StrategyDefinition",
              "frozen": dict(expected), "family_id": FAMILY,
              "attempt_states": {v: "PENDING" for v in VERSIONS},
              "attempt_checkpoint": list(attempt_checkpoint),
              "evidence_checkpoint": list(evidence_checkpoint),
              "pilot_result_digest": result["result_digest"],
              "cost_assumptions": COSTS, "versions": summaries,
              "selection": "NONE", "promotion": "NONE",
              "independent_custody": "NOT_VERIFIED",
              "oos": "NOT_OPENED", "paper": "NOT_STARTED",
              "actual_fills": "NOT_OBSERVED",
              "warnings": ["Synthetic test bars only; not financial/strategy validation",
                           "Neither pilot nor evidence proves external prior custody",
                           "UNKNOWN, unresolved boundary and terminal open positions are not closed PnL"]}
    report["report_digest"] = digest(report)
    return report


def verify_workflow(db_path, *, expected, expected_report_digest,
                    expected_attempt_checkpoint, expected_evidence_checkpoint):
    """Reopen and verify original retained hash/ledger/report commitments.

    Require caller-supplied previously retained digests/checkpoints; no
    self-issued external trust anchor or mutable cached summary.
    """
    frozen = _verify_frozen(expected)
    for value in (expected_attempt_checkpoint, expected_evidence_checkpoint):
        if (type(value) is not tuple or len(value) != 2 or type(value[0]) is not int
                or type(value[1]) is not str or len(value[1]) != 64):
            raise ValueError("Explicit checkpoint tuple required")
    if type(expected_report_digest) is not str or len(expected_report_digest) != 64:
        raise ValueError("Expected report digest required")
    if not Path(db_path).is_file():
        raise ValueError("Existing sealed Factory ledger required")
    ledger = AttemptLedger(db_path, expected_checkpoint=expected_attempt_checkpoint)
    db = ledger._connect()
    try:
        db.execute("BEGIN")
        enrolled = db.execute(
            "SELECT plan_digest,plan_bytes FROM frozen_plan_policy WHERE id=1").fetchone()
        if (enrolled is None or enrolled[0] != expected["family_digest"]
                or bytes(enrolled[1]) != frozen["family_plan"]):
            raise ValueError("Frozen family contents mismatch")
        events, actual_checkpoint = ledger._read(db)
    finally:
        if db.in_transaction:
            db.execute("ROLLBACK")
        db.close()
    if actual_checkpoint != expected_attempt_checkpoint:
        raise ValueError("Attempt ledger changed since committed report")
    if (len(events) != 2
            or set((e["candidate_id"], e["state"], e["strategy_digest"],
                    e["input_digest"]) for e in events) != set(
                    (v, "PENDING", version_digest(v), expected["fixture_digest"])
                    for v in VERSIONS)
            or any(e["family_id"] != FAMILY for e in events)):
        raise ValueError("Exactly two sealed PENDING version receipts required")
    evidence, checkpoint = read_synthetic_evidence(
        ledger, expected_evidence_checkpoint=expected_evidence_checkpoint)
    if checkpoint != expected_evidence_checkpoint:
        raise ValueError("Synthetic evidence checkpoint mismatch")
    plan = PilotPlan(SPEC)
    result = run_pilot(synthetic_fixture(), plan=plan,
                       expected_plan_digest=expected["pilot_plan_digest"],
                       expected_data_digest=expected["fixture_digest"])
    report = _report(result, evidence, checkpoint, actual_checkpoint, expected)
    if report["report_digest"] != expected_report_digest:
        raise ValueError("Retained report digest mismatch")
    return report


def run_workflow(db_path, *, expected):
    """Create/replay a single synthetic Factory family on an explicit DB path.

    This entry point never exports or persists its own 'trusted' anchor.
    The caller must independently retain the returned expected digests.
    """
    frozen = _verify_frozen(expected)
    plan = PilotPlan(SPEC)
    bars = synthetic_fixture()
    ledger = AttemptLedger(db_path)
    writer = FrozenAttemptWriter(ledger, frozen["family_plan"], expected["family_digest"])
    prior, _ = ledger.snapshot()
    ids = {e["candidate_id"] for e in prior}
    if prior and (len(prior) != 2 or ids != set(VERSIONS)):
        raise ValueError("Existing Factory attempts are not this exact synthetic family")
    for v in VERSIONS:
        if v not in ids:
            writer.record_attempt({"state": "PENDING", "family_id": FAMILY,
                                   "candidate_id": v, "input_digest": expected["fixture_digest"],
                                   "strategy_digest": version_digest(v)})
    events, attempt_checkpoint = ledger.snapshot()
    if len(events) != 2 or any(e["state"] != "PENDING" for e in events):
        raise ValueError("Synthetic attempts must remain PENDING")
    result = run_pilot(bars, plan=plan,
                       expected_plan_digest=expected["pilot_plan_digest"],
                       expected_data_digest=expected["fixture_digest"])
    evidence_checkpoint, _ = record_synthetic_result(
        writer, raw_plan=frozen["family_plan"],
        expected_family_digest=expected["family_digest"],
        plan=plan, expected_plan_digest=expected["pilot_plan_digest"],
        bars=bars, expected_data_digest=expected["fixture_digest"], result=result)
    report = verify_workflow(
        db_path, expected=expected, expected_report_digest=_report(
            result, read_synthetic_evidence(ledger)[0], evidence_checkpoint,
            attempt_checkpoint, expected)["report_digest"],
        expected_attempt_checkpoint=attempt_checkpoint,
        expected_evidence_checkpoint=evidence_checkpoint)
    return report


def report_json(report):
    """Canonical machine-readable bytes. No claim of trusted prior publication."""
    if type(report) is not dict or report.get("schema") != "sf-synthetic-workflow-report-1":
        raise ValueError("Validated synthetic workflow report required")
    if digest({k: v for k, v in report.items() if k != "report_digest"}) != report.get("report_digest"):
        raise ValueError("Report digest mismatch")
    return canonical(report)


def report_summary(report):
    """Compact readable summary; never a promotion recommendation."""
    report_json(report)
    lines = ["SF-DEC-21 B — SYNTHETIC INTEGRATION ONLY",
             "Report digest: " + report["report_digest"],
             "Family: " + report["family_id"],
             "Result digest: " + report["pilot_result_digest"]]
    for name in VERSIONS:
        entry = report["versions"][name]
        lines.append(name + ": " + str(entry["counts"]["closed_trades"]) +
                     " closed hypothetical trades; unresolved=" +
                     str(entry["counts"]["unresolved_boundary"]) +
                     "; terminal_open=" + str(entry["counts"]["terminal_open_position"]))
    lines.append("No independent custody, research COMPLETE, OOS, PAPER, trading or promotion.")
    return "\n".join(lines)
