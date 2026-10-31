"""Owner P0 evidence gate; delegates ALL verification to Core's canonical C1 custody.

No substitute data, no bypass, no independent/weaker duplicate parser.
"""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
from research_wp_r0.aql_p0_c1_custody import verify_native_bundle


def verify_owner_evidence(outer_zip: Path, manifest_path: Path, normalized_path: Path) -> dict:
    # Verify the three original byte domains together, including all 672 rows,
    # publisher checksum files, UTC inventory, and the seven nested daily ZIPs.
    source_sha = verify_native_bundle(
        outer_zip.read_bytes(), manifest_path.read_bytes(), normalized_path.read_bytes()
    )
    return {
        "status": "OWNER_SOURCE_BYTES_VERIFIED",
        "source_bytes_sha256": source_sha,
        "verification": "CORE_C1_VERIFY_NATIVE_BUNDLE",
        "availability_mode": "RETROSPECTIVE_NON_PIT",
        "limitations": "Native byte custody only; no historical arrival/PIT attestation.",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--outer-zip", required=True, type=Path)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--normalized", required=True, type=Path)
    parser.add_argument("--receipt", required=True, type=Path)
    args = parser.parse_args()
    result = verify_owner_evidence(args.outer_zip, args.manifest, args.normalized)
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    encoded = (json.dumps(result, sort_keys=True, separators=(",", ":")) + "\n").encode()
    with args.receipt.open("xb") as fh:
        fh.write(encoded)
        fh.flush()
        os.fsync(fh.fileno())
    if args.receipt.read_bytes() != encoded:
        raise RuntimeError("OWNER_SOURCE_RECEIPT_READBACK_MISMATCH")
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
