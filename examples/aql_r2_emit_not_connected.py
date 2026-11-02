"""Reproducible R2 offline NOT_CONNECTED proof (no synthetic G2 decision).

The artifact asserts a capability boundary only, never original strategy evidence.
"""
from __future__ import annotations

import argparse
import hashlib
import os
from pathlib import Path

from research_wp_r0.aql_f1_decision_capture_v1 import jcs_bytes
from research_wp_r0.aql_r2_original_decision_ingress import capture_original_g2_pair

SCHEMA = "aql.r2-original-decision-ingress.v1"


def build_disconnected_report() -> bytes:
    # Identity is an explicit absent-producer capability check, NOT a
    # manufactured opportunity or a prospective source-time event.
    outcome = capture_original_g2_pair(
        c2={"availability_mode": "PROSPECTIVE_CAPTURE",
            "opportunity_id": "NOT_CONNECTED_NO_REAL_G2_EVENT"},
        plan_sha="0" * 64,
        producer=None,
        registry={},
        journal_dir=Path("/NOT_USED_NO_WRITES"),
        pre_f3_gate=lambda _: False,
    )
    if outcome["connection_status"] != "NOT_CONNECTED":
        raise RuntimeError("R2_DISCONNECTED_GATE_BROKEN")
    if outcome["arm_statuses"] != {"BASE": "MISSING_CAPTURE", "SHADOW": "MISSING_CAPTURE"}:
        raise RuntimeError("R2_DENOMINATOR_GATE_BROKEN")
    if "pair_id" in outcome or "handoff_sha256" in outcome:
        raise RuntimeError("R2_FALSE_ORIGINAL_ARTIFACT_PROOF")
    return jcs_bytes(outcome) + b"\n"


def write_report(path: Path) -> str:
    data = build_disconnected_report()
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL |
                 getattr(os, "O_NOFOLLOW", 0), 0o600)
    try:
        if os.write(fd, data) != len(data):
            raise RuntimeError("R2_SHORT_WRITE")
        os.fsync(fd)
    finally:
        os.close(fd)
    if path.read_bytes() != data:
        raise RuntimeError("R2_READBACK_MISMATCH")
    return hashlib.sha256(data).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description="R2 NOT_CONNECTED no-trade proof")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    print("sha256=" + write_report(args.out))


if __name__ == "__main__":
    main()
