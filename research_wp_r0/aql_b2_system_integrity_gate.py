"""B2 Factory fail-closed, read-only SYSTEM_INTEGRITY contract gate.

This gate checks Core's TEST_ONLY handoff and the previously Audit-accepted
B1 market report identity. It does NOT claim a Vault/market-window E2E replay.
Missing connections are explicit NOT_CONNECTED rather than invented PASS.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path

HORIZONS = (14_400_000, 86_400_000, 259_200_000)
ARMS = ("BASE", "SHADOW")
MARKET_SHA = "54316200aa6887cf8f4e7e752c469361fc250aea"


def _sha(blob: bytes) -> str:
    return hashlib.sha256(blob).hexdigest()


def _require(ok: bool, code: str) -> None:
    if not ok:
        raise ValueError(code)


def assess(core: dict, market: dict, *, core_sha: str, market_sha: str) -> dict:
    _require(core.get("schema_version") == "aql.b2-core-factory-integrity-input.v1",
             "INVALID_CORE_SCHEMA")
    _require(core.get("evidence_class") == "TEST_ONLY_CONTROLLED_SYSTEM_INPUT"
             and core.get("original_2024_strategy_decisions_supplied") is False
             and core.get("original_pit_verified") is False
             and core.get("live_f3_connected") is False, "TEST_ONLY_BOUNDARY")
    schedules = core.get("schedule")
    _require(isinstance(schedules, list) and len(schedules) == core.get("n")
             and len(schedules) > 0, "SCHEDULE_DENOMINATOR")
    n = len(schedules)
    _require(core.get("expected_2n") == 2*n
             and core.get("expected_6n") == 6*n
             and core.get("horizons_ms") == list(HORIZONS), "N_2N_6N_MISMATCH")
    pair_ids = [x.get("pair_id") for x in schedules]
    c2 = [json.dumps(x.get("c2_identity"), sort_keys=True) for x in schedules]
    _require(len(set(pair_ids)) == n and len(set(c2)) == n, "DUPLICATE_OPPORTUNITY")
    _require(all(isinstance(x.get("decision_cutoff_ms"), int)
                 and x["decision_cutoff_ms"] % 900_000 == 0 for x in schedules),
             "CUTOFF_NOT_15M_ALIGNED")
    projection = core.get("core_projection")
    _require(isinstance(projection, dict)
             and projection.get("scheduled_pairs") == n
             and projection.get("arm_denominator") == 2*n, "CORE_PROJECTION_DENOMINATOR")
    rows = projection.get("signal_rows")
    _require(isinstance(rows, list) and len(rows) == 2*n, "CORE_ARM_ROW_COUNT")
    expected = {(pair, arm) for pair in pair_ids for arm in ARMS}
    actual = [(x.get("pair_id"), x.get("arm")) for x in rows]
    _require(len(set(actual)) == len(actual) and set(actual) == expected,
             "ARM_LOSS_DUPLICATE_OR_MISASSIGNMENT")
    _require(all(x.get("capture_status") != "RECORDED"
                 and x.get("research_direction") is None
                 and x.get("directional_outcomes_allowed") is False for x in rows),
             "SYNTHETIC_PIT_PROMOTION")
    _require(market.get("schema") == "aql.b1.market-only-report.v1"
             and market.get("scope") == "RETROSPECTIVE_MARKET_ONLY"
             and market.get("observed_bars") == 35136
             and market.get("missing_bars") == 0
             and market.get("duplicate_bars") == 0
             and market.get("operational_pit_proven") is False,
             "B1_MARKET_LOCK_MISMATCH")
    _require(core.get("interface_map", {}).get("market_2024_factory_sha") == MARKET_SHA,
             "MARKET_FACTORY_PIN_DRIFT")
    _require(len(market.get("horizons", [])) == 3
             and [x.get("horizon_hours") for x in market["horizons"]] == [4,24,72],
             "MARKET_HORIZON_SCHEMA")
    _require(all(x["complete"] + x["censored"] == 35136
                 for x in market["horizons"]), "MARKET_HORIZON_DENOMINATOR")
    status = dict(sorted(Counter(x["capture_status"] for x in rows).items()))
    seams = {
        "core_schedule_to_f1_status": "PASS_CONTRACT_ONLY",
        "original_2024_market_source": "ACCEPT_BOUNDED_PRIOR_AUDIT",
        "core_to_factory_market_window_join": "NOT_CONNECTED",
        "vault_parent_external_custody": "NOT_CONNECTED",
        "monitor_snapshots_to_outcomes": "NOT_CONNECTED",
        "actual_prospective_producer_to_f3": "NOT_CONNECTED",
        "directional_tp_sl_and_fills": "NOT_TESTED",
        "operational_pit": "BLOCKED_EXTERNAL_EVIDENCE",
    }
    return {
        "schema": "aql.b2.factory-system-integrity-gate.v1",
        "scope": "CONTROLLED_E2E_PARTIAL_CONTRACT_GATE",
        "result": "BLOCKED_NOT_END_TO_END",
        "n": n, "expected_2n": 2*n, "observed_2n": len(rows),
        "expected_6n": 6*n, "observed_6n": None,
        "capture_statuses": status,
        "core_input_sha256": core_sha, "b1_market_report_sha256": market_sha,
        "factory_market_sha": MARKET_SHA,
        "seams": seams,
        "no_alpha_or_pnl_claim": True, "no_g0_or_deployment_authorized": True,
        "next_action": "Run pinned Core/Factory/Vault overlay against verified original 2024 OHLC bytes; report missing seams, negative cases and deterministic replay",
    }


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--core", type=Path, required=True)
    p.add_argument("--market-report", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    a = p.parse_args()
    cb, mb = a.core.read_bytes(), a.market_report.read_bytes()
    result = assess(json.loads(cb), json.loads(mb),
                    core_sha=_sha(cb), market_sha=_sha(mb))
    raw = (json.dumps(result, sort_keys=True, separators=(",", ":")) + "\n").encode()
    if a.out.exists():
        raise FileExistsError("REFUSE_OVERWRITE")
    a.out.write_bytes(raw)
    print("SYSTEM_INTEGRITY_SHA256=" + _sha(raw))
    print("RESULT=" + result["result"])


if __name__ == "__main__":
    main()
