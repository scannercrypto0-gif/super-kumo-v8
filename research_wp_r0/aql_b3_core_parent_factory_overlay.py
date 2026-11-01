"""B3 exact Core parent -> actual Vault -> actual Factory verified consumer.

Read-only pinned Core #216 B3 code is loaded through CI overlay; actual Vault
#211 methods admit/read/manifest are exercised in an ephemeral local vault.
This run is TEST_ONLY, preserving Core's F1 original SHA/cutoff/source vintage.
No self-issued Vault receipt can authorize independent PIT, market or F3 proof.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from research_wp_r0.aql_f1_b3_vault_parent_adapter import (
    parent_input_for_pair, exercised_vault_parent, bound_parent_evidence,
)
from research_wp_r0.aql_f1_parent_witness_v1 import validate_parent_binding
from research_wp_r0.aql_f1_decision_capture_v1 import jcs_bytes
from research_wp_r0.aql_w1_f1_prospective_consumer import (
    project_parent_authenticated_f1_slots,
)
from tools.raw_vault_offline.vault import RawVault
from tools.raw_vault_offline import schema as vault_schema

CORE_B2_DIGEST = "42005d09e3674420ddd8a761d40540c8e6509e8e79943d1f6a9821f692823b09"
CORE_B3_DIGEST = "01a934a90dc6ca72e7b1fca8b352fd1f425d9c0a9eb4c05c9d59a8c3ed69400b"
CORE_B3_HEAD = "17955e295263340b5cfbcfed8ae8e2a3e8a70c32"
VAULT_HEAD = "2ddfb2f4a6e145c6579820beb03e4d678594de21"
FACTORY_B2_HEAD = "ac7f160005672140a3254eb2ed82f4d586432b69"
HORIZONS = (14_400_000, 86_400_000, 259_200_000)


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def fail_if(not_ok, label):
    if not_ok:
        raise ValueError(label)


def run_pinned_core_parent_factory(core_bytes: bytes, handoff_bytes: bytes,
                                   vault_root: Path) -> dict:
    fail_if(sha(core_bytes) != CORE_B2_DIGEST, "PINNED_CORE_B2_INPUT_DRIFT")
    fail_if(sha(handoff_bytes) != CORE_B3_DIGEST, "PINNED_CORE_B3_HANDOFF_DRIFT")
    core = json.loads(core_bytes)
    handoff = json.loads(handoff_bytes)
    plans = core["schedule"]
    candidates = core["original_candidates_test_only"]
    n = len(plans)
    fail_if(core.get("original_pit_verified") is not False
            or core.get("evidence_class") != "TEST_ONLY_CONTROLLED_SYSTEM_INPUT"
            or handoff.get("evidence_class") != "TEST_ONLY_NOT_VENDOR_ORIGINAL_2024"
            or handoff.get("original_pit") is not False, "UNAUTHORIZED_TEST_ONLY_PROMOTION")
    fail_if(n != 2 or core["expected_2n"] != 2*n or core["expected_6n"] != 6*n
            or handoff["n"] != n or handoff["expected_2n"] != 2*n
            or handoff["expected_6n"] != 6*n, "N_2N_6N_PIN_MISMATCH")
    fail_if(handoff["core_b2_contract_sha256"] != CORE_B2_DIGEST
            or handoff["pinned_vault_sha"] != VAULT_HEAD,
            "CORE_B3_DEPENDENCY_PIN_DRIFT")
    fail_if(len(set(p["pair_id"] for p in plans)) != n
            or sorted(handoff["original_f1_pair_ids"])
            != sorted(p["pair_id"] for p in plans), "PAIR_ID_DUPLICATE_OR_DRIFT")
    parents = {x["pair_id"]: x for x in handoff["vault_parents"]}
    fail_if(len(parents) != n or set(parents) != {p["pair_id"] for p in plans},
            "CORE_B3_VAULT_PARENT_COUNT")
    expected_arm_sha = {(r["pair_id"], r["arm"]): r["f1_record_sha256"]
                        for r in candidates}
    fail_if(len(expected_arm_sha) != 2*n, "CORE_ORIGINAL_F1_ARMS")
    supplied = handoff["arm_bindings"]
    fail_if(len(supplied) != 2*n or len({x["f1_record_sha256"] for x in supplied}) != 2*n,
            "CORE_B3_ARM_BINDING_COUNT_OR_DUPLICATE")
    supplied_by_sha = {x["f1_record_sha256"]: x for x in supplied}
    fail_if(set(supplied_by_sha) != set(expected_arm_sha.values()), "F1_SHA_BINDING_DRIFT")
    vault = RawVault(vault_root)
    readback_parent_by_pair, readback_manifest_by_pair = {}, {}
    bound_pairs, bound_arms = [], []
    for plan in plans:
        pair = plan["pair_id"]
        originals = [r for r in candidates if r["pair_id"] == pair]
        from_core = parent_input_for_pair(plan, originals)
        retained = exercised_vault_parent(from_core, vault, vault_schema)
        given = parents[pair]
        for k in ("vault_parent_sha256", "vault_manifest_record_sha256",
                  "vault_logical_identity_key", "f1_source_bytes_sha256",
                  "f1_original_record_sha256_by_arm", "vault_manifest_record"):
            fail_if(retained[k] != given[k], "CORE_VAULT_PARENT_OR_MANIFEST_EVIDENCE_DRIFT_"+k)
        fail_if(retained["vault_parent_sha256"] == plan["source_bytes_sha256"],
                "RAW_PARENT_SHA_WRONGLY_EQUAL_F1_DERIVED_PREFIX")
        # Return ACTUAL Vault.read bytes to Factory's parent bridge, never
        # reconstruct a market witness or swap with unchecked input.
        parent = vault.read(retained["vault_parent_sha256"])
        fail_if(sha(parent) != retained["vault_parent_sha256"],
                "RAW_PARENT_POST_VAULT_READBACK_DIGEST")
        readback_parent_by_pair[pair] = parent
        readback_manifest_by_pair[pair] = retained["vault_manifest_record"]
        bound_pairs.append({
            "pair_id": pair,
            "raw_parent_sha256": sha(parent),
            "manifest_record_sha256": retained["vault_manifest_record_sha256"],
            "vault_lid": retained["vault_logical_identity_key"],
            "original_F1_source_pin_sha256": plan["source_bytes_sha256"],
            "manifest_evidence_class": retained["vault_manifest_record"]["evidence_class"],
            "source_clock_authoritative": False,
            "actual_RawVault_admit_read_manifest": "PASS",
        })
        for record in originals:
            actual_binding = bound_parent_evidence(
                record, retained,
                source_published_at_ms=record["source_available_at_ms"],
                source_finalized_at_ms=record["source_asof_ms"],
                correction_published_at_ms=record["source_available_at_ms"],
            )
            original = supplied_by_sha[record["f1_record_sha256"]]
            fail_if(original["arm"] != record["arm"] or original["binding"] != actual_binding,
                    "ORIGINAL_CORE_B3_ARM_PARENT_BINDING_DRIFT")
            binding = actual_binding["raw_parent_binding"]
            # Must NOT treat controlled positive test callback as external witness.
            no_external = validate_parent_binding(
                record, binding, parent_bytes=retained["parent_bytes"],
                parent_manifest_bytes=retained["manifest_bytes"],
                parent_witness=None,
            )
            fail_if(no_external or actual_binding["independent_parent_proof"] is not False
                    or actual_binding["structural_parent_binding_test_only"] is not True,
                    "FAKE_PARENT_WITNESS_PROMOTED_TO_PIT")
            bound_arms.append({"pair_id": pair, "arm": record["arm"],
                               "original_f1_record_sha256": record["f1_record_sha256"],
                               "raw_parent_binding_sha256": binding["parent_binding_sha256"],
                               "status": "STRUCTURAL_TEST_PASS_EXTERNAL_PROOF_BLOCKED"})
    recovery = vault.recovery_scan()
    fail_if(recovery.get("status") != "CLEAN", "RAW_VAULT_RECOVERY_INTEGRITY_FAIL")
    fail_if(len(vault.manifest_entries()) != n, "RAW_VAULT_MANIFEST_N")
    # This is the REAL Factory parent market consumer. The Core B3 parent
    # is JSON_LINES TEST_ONLY, not authenticated original 15m issuer data,
    # and there are no independently witnessed derived market windows.
    # The correct output is UNKNOWN/UNVERIFIED across all 6N outcomes.
    projected = project_parent_authenticated_f1_slots(
        plans, candidates,
        parent_bytes_by_pair=readback_parent_by_pair,
        manifest_by_pair=readback_manifest_by_pair,
        derived_bars_by_pair={}, derived_evidence_by_pair={},
        indicator_registry=core["indicator_registry"],
        verify_parent_manifest=None, verify_derivation=None,
        verify_external_receipt=None, proof_verifier=None,
    )
    outcomes = projected["outcomes"]
    expected_outcomes = {(p["pair_id"], arm, h) for p in plans
                         for arm in ("BASE", "SHADOW") for h in HORIZONS}
    got_outcomes = {(x["pair_id"], x["arm"], x["horizon_ms"]) for x in outcomes}
    fail_if(projected["scheduled_total"] != n
            or projected["arm_slots"] != 2*n
            or projected["outcome_rows"] != 6*n
            or got_outcomes != expected_outcomes
            or len(got_outcomes) != len(outcomes), "FACTORY_MISSING_DUPLICATED_OR_MISASSIGNED")
    fail_if(any(x["capture_status"] != "UNVERIFIED"
                or x["coverage_status"] != "UNKNOWN"
                or x["max_favorable"] is not None
                or x["max_adverse"] is not None
                or x["no_fill_or_pnl_inference"] is not True for x in outcomes),
            "FACTORY_PIT_OR_SIGNED_METRIC_FALSE_PROMOTION")
    fail_if(projected["independent_parent_verifiers_supplied"] is not False
            or projected["operational_pit_and_custody_proven"] is not False,
            "FACTORY_LOCAL_CUSTODY_MISREPORTED_AS_EXTERNAL")
    return {
        "schema": "aql.b3.factory-core-parent-vault-consumer-run.v1",
        "scope": "TEST_ONLY_ACTUAL_CORE_PARENT_VAULT_FACTORY_SOFTWARE_INTEGRATION",
        "result": "PASS_CONTROLLED_LOCAL_CORE_PARENT_VAULT_FACTORY_BOUNDARY",
        "pins": {"core_b2_sha256": CORE_B2_DIGEST,
                 "core_b3_sha256": CORE_B3_DIGEST,
                 "core_b3_head": CORE_B3_HEAD,
                 "factory_b2_base_head": FACTORY_B2_HEAD,
                 "vault_head": VAULT_HEAD},
        "N": n, "expected_2N": 2*n, "observed_2N": projected["arm_slots"],
        "expected_6N": 6*n, "observed_6N": projected["outcome_rows"],
        "local_vault_recovery": "CLEAN",
        "real_vault_parent_objects": bound_pairs,
        "core_parent_original_F1_arm_bindings": bound_arms,
        "consumer_capture_statuses": "UNVERIFIED_4_OF_4",
        "consumer_market_coverage": "UNKNOWN_12_OF_12",
        "per_seam": {
            "Core_B3_parent_bytes_to_real_RawVault_admit_readback": "PASS_LOCAL_SOFTWARE",
            "real_RawVault_manifest_parent_sha_to_Core_original_F1_binding": "PASS_STRUCTURAL_ONLY",
            "readback_Core_parent_to_real_Factory_parent_consumer": "PASS_FAIL_CLOSED",
            "source_derived_market_windows_with_independent_witness": "BLOCKED_EXTERNAL_EVIDENCE",
            "original_historical_2024_strategy_F1": "NOT_SUPPLIED",
            "external_issuer_custody_correction_clock": "BLOCKED_EXTERNAL_EVIDENCE",
            "monitor_snapshots_to_outcomes": "NOT_CONNECTED",
            "real_prospective_producer_to_F3": "NOT_CONNECTED",
            "TP_SL_fills_or_profitability": "NOT_TESTED",
        },
        "pit_or_g0_authorized": False, "no_merge_or_deploy": True,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--core-b2", type=Path, required=True)
    parser.add_argument("--core-b3", type=Path, required=True)
    parser.add_argument("--vault-root", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    opts = parser.parse_args()
    fail_if(opts.out.exists(), "IMMUTABLE_REPORT_OVERWRITE_REFUSED")
    report = run_pinned_core_parent_factory(
        opts.core_b2.read_bytes(), opts.core_b3.read_bytes(), opts.vault_root)
    opts.out.parent.mkdir(parents=True, exist_ok=True)
    raw = jcs_bytes(report) + b"\n"
    opts.out.write_bytes(raw)
    print("FACTORY_B3_INTEGRATED_SHA256=" + sha(raw))
    print("FACTORY_B3_INTEGRATED_RESULT=" + report["result"])
    print("N/2N/6N=" + "/".join(map(str, (report["N"], report["observed_2N"], report["observed_6N"]))))


if __name__ == "__main__":
    main()
