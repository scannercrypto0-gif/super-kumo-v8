"""CLI: exact B1 market-only original-archive artifact -> Core R1 research JSON.

No publisher download or historical F1 reconstruction. Exit nonzero when the
source artifact ZIP, monthly vendor archive/member checksum or cutoff is wrong.
"""
from __future__ import annotations

import argparse
import hashlib
from pathlib import Path

from research_wp_r0.aql_r1_market_research_producer import (
    build_handoff, canonical, load_pinned_originals,
)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--b1-artifact", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    a = p.parse_args()
    if a.out.exists():
        raise ValueError("REFUSE_OVERWRITE_R1_HANDOFF")
    months, source = load_pinned_originals(a.b1_artifact.read_bytes())
    output = build_handoff(months, source)
    raw = canonical(output)
    a.out.parent.mkdir(parents=True, exist_ok=True)
    with a.out.open("xb") as f:
        f.write(raw)
        f.flush()
        import os
        os.fsync(f.fileno())
    if a.out.read_bytes() != raw:
        raise RuntimeError("R1_HANDOFF_READBACK_MISMATCH")
    counts = output["counts"]
    print("R1_CORE_SHA256=" + hashlib.sha256(raw).hexdigest())
    print("R1_N={n_opportunities} 2N={arm_slots_2n} 6N={expected_outcome_rows_6n}".format(**counts))
    print("R1_FEATURE_READY=" + str(counts["features_ready"]))
    print("R1_ORIGINAL_DECISIONS=MISSING_CAPTURE")
    print("R1_ISSUER_CLOCK_FREEZE=BLOCKED_EXTERNAL_EVIDENCE")


if __name__ == "__main__":
    main()
