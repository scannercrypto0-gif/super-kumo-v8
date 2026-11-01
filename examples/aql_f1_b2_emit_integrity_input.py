"""One bounded B2 Core test-only runner, no live market reads or F3 execution.

The output preserves original TEST_ONLY candidate bytes (including source pins
and indicator snapshots). Factory does its own market/Vault integration.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import tempfile
from pathlib import Path

from research_wp_r0.aql_f1_b2_integrity_input import (
    make_b2_test_records, make_b2_evidence_contract,
)
from research_wp_r0.aql_f1_decision_capture_v1 import jcs_bytes
from research_wp_r0.aql_f1_prospective_host_v1 import run_prospective_host


def build_b2_input() -> dict:
    schedules, originals, registry = make_b2_test_records()
    all_handoffs = []
    with tempfile.TemporaryDirectory(prefix="aql_b2_test_only_") as directory:
        for i, plan in enumerate(schedules):
            identity = plan["c2_identity"]
            by_arm = {
                row["arm"]: row
                for row in originals
                if row["pair_id"] == plan["pair_id"]
            }
            if set(by_arm) != {"BASE", "SHADOW"}:
                raise ValueError("B2_CANDIDATE_INCOMPLETE")
            base = by_arm["BASE"]
            c2 = {
                **identity,
                "availability_mode": "PROSPECTIVE_CAPTURE",
                "decision_cutoff_ms": base["decision_cutoff_ms"],
                "run_manifest_sha256": base["run_manifest_sha256"],
                "prefix_end_exclusive_ms": base["prefix_end_exclusive_ms"],
                "prefix_bar_checksums_sha256": base["prefix_bar_checksums_sha256"],
                "gap_inventory_sha256": base["gap_inventory_sha256"],
                "correction_lineage_sha256": base["correction_lineage_sha256"],
            }
            all_handoffs.append(run_prospective_host(
                c2, base["experiment_plan_sha256"], by_arm, registry,
                Path(directory) / f"opportunity_{i+1}",
                pre_f3_gate=lambda _: True,
            ))
    contract = make_b2_evidence_contract(
        schedules, originals, all_handoffs, registry
    )
    assert contract["n"] == 2
    assert contract["expected_2n"] == 4
    assert contract["expected_6n"] == 12
    return contract


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    opts = parser.parse_args()
    data = build_b2_input()
    raw = jcs_bytes(data) + b"\n"
    opts.out.parent.mkdir(parents=True, exist_ok=True)
    opts.out.write_bytes(raw)
    if opts.out.read_bytes() != raw:
        raise RuntimeError("B2_READBACK_MISMATCH")
    print("CORE_B2_SHA256=" + hashlib.sha256(raw).hexdigest())
    print("N=2 2N=4 6N=12; TEST_ONLY, UNVERIFIED")
    print("FACTORY_2024_MARKET_ONLY=ACCEPT_BOUNDED")
    print("REAL_F3_PRODUCER=NOT_CONNECTED; OPERATIONAL_PIT=BLOCKED")


if __name__ == "__main__":
    main()
