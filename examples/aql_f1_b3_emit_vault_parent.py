"""Single B3 Core->real #211 RawVault admit/readback test-only connector.

Requires pinned #211 schema/vault paths in PYTHONPATH by exact-SHA CI overlay.
No Factory stub, no historical F1 source forgery, no real external custody.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import tempfile
from pathlib import Path

from examples.aql_f1_b2_emit_integrity_input import build_b2_input
from research_wp_r0.aql_f1_decision_capture_v1 import digest, jcs_bytes
from research_wp_r0.aql_f1_b3_vault_parent_adapter import (
    B2_INPUT_SHA256, VAULT_PIN, FIXTURE_ORIGIN,
    bound_parent_evidence, exercised_vault_parent, make_vault_meta,
    parent_input_for_pair, report_safe_pair,
)
from tools.raw_vault_offline.vault import RawVault
from tools.raw_vault_offline import schema as schema


def exercise_b3_connection() -> dict:
    b2 = build_b2_input()
    original_b2_bytes = jcs_bytes(b2) + b"\n"
    if hashlib.sha256(original_b2_bytes).hexdigest() != B2_INPUT_SHA256:
        raise RuntimeError("B3_B2_INPUT_SHA_MISMATCH")
    parents, bindings = [], []
    with tempfile.TemporaryDirectory(prefix="aql_b3_vault_") as tmp:
        vault = RawVault(Path(tmp))
        for plan in b2["schedule"]:
            record_pair = [r for r in b2["original_candidates_test_only"]
                           if r["pair_id"] == plan["pair_id"]]
            parent = parent_input_for_pair(plan, record_pair)
            retained = exercised_vault_parent(parent, vault, schema)
            pair_rows = []
            for original in record_pair:
                pair_rows.append({
                    "arm": original["arm"],
                    "f1_record_sha256": original["f1_record_sha256"],
                    "binding": bound_parent_evidence(
                        original, retained,
                        source_published_at_ms=original["source_available_at_ms"],
                        source_finalized_at_ms=original["source_asof_ms"],
                        correction_published_at_ms=original["source_available_at_ms"],
                    ),
                })
            parents.append(report_safe_pair(retained))
            bindings.extend(pair_rows)
        if len(vault.manifest_entries()) != 2:
            raise RuntimeError("B3_VAULT_UNEXPECTED_MANIFEST_DENOMINATOR")
        # Recovery consistency is a real Vault code check, no mocked writes.
        recovery = vault.recovery_scan()
        if recovery.get("status") != "CLEAN":
            raise RuntimeError("B3_VAULT_RECOVERY_NOT_CLEAN")
    if len(bindings) != 4 or not all(
        row["binding"]["structural_parent_binding_test_only"] is True and
        row["binding"]["independent_parent_proof"] is False
        for row in bindings
    ):
        raise RuntimeError("B3_PARENT_BINDING_NOT_FAIL_CLOSED")
    return {
        "schema_version": "aql.b3-core-vault-parent-handoff.v1",
        "evidence_class": FIXTURE_ORIGIN,
        "core_b2_contract_sha256": B2_INPUT_SHA256,
        "pinned_vault_sha": VAULT_PIN,
        "pinned_factory_b2_sha": "ac7f160005672140a3254eb2ed82f4d586432b69",
        "n": 2, "expected_2n": 4, "expected_6n": 12,
        "original_f1_pair_ids": [p["pair_id"] for p in b2["schedule"]],
        "original_core_f1_record_sha256": {
            r["pair_id"] + ":" + r["arm"]: r["f1_record_sha256"]
            for r in b2["original_candidates_test_only"]
        },
        "vault_admit_readback": "PASS_LOCAL_VAULT_SOFTWARE_SEAM",
        "vault_recovery_status": recovery["status"],
        "vault_parents": parents,
        "arm_bindings": bindings,
        "independent_source_issuer_custody_clock": "BLOCKED_EXTERNAL_EVIDENCE",
        "original_pit": False,
        "factory_full_consumption": "NOT_EXECUTED_BY_CORE_HANDOFF",
        "prospective_f3": "NOT_CONNECTED",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    report = exercise_b3_connection()
    raw = jcs_bytes(report) + b"\n"
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_bytes(raw)
    if args.out.read_bytes() != raw:
        raise RuntimeError("B3_HANDOFF_READBACK_MISMATCH")
    print("B3_CORE_VAULT_PARENT_SHA256=" + hashlib.sha256(raw).hexdigest())
    print("N=2 2N=4 6N=12; actual Vault.admit/read/manifest_entries/recovery_scan")
    print("EXTERNAL_ISSUER_CLOCK_CUSTODY=BLOCKED_EXTERNAL_EVIDENCE")


if __name__ == "__main__":
    main()
