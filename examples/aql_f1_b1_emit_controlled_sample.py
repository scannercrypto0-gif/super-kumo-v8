"""Reproducible B1 CONTROLLED_ONLY signal-to-Factory research sample.

Uses test fixtures, not original issuer market data. Must never be interpreted
as a PIT study, production signal, executable entry, or PnL. Run on pinned
Core+Factory read-only overlay job; no branch merge or trading writes.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import tempfile
from pathlib import Path

from research_wp_r0.aql_f1_decision_capture_v1 import digest, hash_f1
from research_wp_r0.aql_f1_prospective_host_v1 import run_prospective_host
from research_wp_r0.aql_f1_research_signal_handoff_v1 import project_original_signal_handoffs
from research_wp_r0.aql_w1_f1_prospective_consumer import project_core_verified_f1_slots
from tests.test_aql_f1_decision_capture_v1 import fixture
from tests.test_aql_f1_prospective_bridge import envelope
from tests.test_aql_f1_b1_research_signal_handoff import _schedule


FACTORY_SHA = "e52a9fb9d091ce439278988bdb0c7ef4ffaeab99"


def make_controlled_sample() -> dict:
    records = []
    scheduled = []
    handoffs = []
    with tempfile.TemporaryDirectory() as root:
        for i in range(2):
            base, registry = fixture("BASE", state="ARMED" if i == 0 else "NO_SIGNAL",
                                     direction="LONG" if i == 0 else None,
                                     eligible="YES" if i == 0 else "NOT_ESTABLISHED")
            shadow, _ = fixture("SHADOW")
            for candidate in (base, shadow):
                candidate["strategy_id"] = "SF_BREAKOUT_BASE_20_10_DEV_v1"
                candidate["c2_identity"]["opportunity_id"] = f"CONTROLLED_OPP_{i + 1}"
                candidate["opportunity_id"] = candidate["c2_identity"]["opportunity_id"]
                candidate["pair_id"] = digest({
                    "experiment_plan_sha256": candidate["experiment_plan_sha256"],
                    "c2_identity": candidate["c2_identity"]})
            if i == 0:
                for name, level in (("tp", "110"), ("sl", "90")):
                    base[name] = dict(
                        status="DEFINED_PREDECISION", level=level, unit="USDT",
                        basis="ABSOLUTE", reference_price_kind="bar-close",
                        defined_at_ms=base["decision_cutoff_ms"],
                        tick_size="0.01", decimal_scale=2, rounding_mode="HALF_EVEN")
            for candidate in (base, shadow):
                candidate["f1_record_sha256"] = hash_f1(candidate)
            handoffs.append(run_prospective_host(
                envelope(base), base["experiment_plan_sha256"],
                {"BASE": base, "SHADOW": shadow}, registry, Path(root) / str(i),
                pre_f3_gate=lambda _: True))
            scheduled.append(_schedule(base))
            records.extend((base, shadow))
        core = project_original_signal_handoffs(
            scheduled, handoffs, records, registry)
        factory = project_core_verified_f1_slots(
            scheduled, records, indicator_registry=registry)
    assert core["arm_denominator"] == 4
    assert factory["arm_slots"] == 4 and factory["outcome_rows"] == 12
    assert all(x["capture_status"] == "UNVERIFIED" and
               x["research_direction"] is None and
               not x["directional_outcomes_allowed"] for x in core["signal_rows"])
    assert all(x["measurement_class"] == "MARKET_ONLY" and
               x["max_favorable"] is None and
               x["max_adverse"] is None for x in factory["outcomes"])
    return {
        "schema_version": "aql.b1-controlled-research-sample.v1",
        "controlled_fixture_only": True,
        "genuine_original_pit_proven": False,
        "external_evidence_status": "BLOCKED_EXTERNAL_EVIDENCE",
        "factory_pin_sha": FACTORY_SHA,
        "original_fixture_labels": [
            "SYNTHETIC_F1_CANDIDATES",
            "SYNTHETIC_PRE_F3_GATE",
            "NO_INDEPENDENT_SOURCE_CLOCK_OR_CUSTODY",
        ],
        "scheduled": scheduled,
        "core_signal_handoff": core,
        "factory_read_only_projection": factory,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    output = make_controlled_sample()
    raw = (json.dumps(output, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False) + "\n").encode("utf-8")
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_bytes(raw)
    print("CONTROLLED_ONLY SAMPLE SHA256=" + hashlib.sha256(raw).hexdigest())
    print("PAIRS=2 ARM_SLOTS=4 FACTORY_OUTCOME_ROWS=12")
    print("PIT/CUSTODY=BLOCKED_EXTERNAL_EVIDENCE")


if __name__ == "__main__":
    main()
