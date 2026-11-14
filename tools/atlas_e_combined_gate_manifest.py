"""Package E cross-owner bounded gate manifest: never hide historical blockers.

Run AFTER pinned owner checkout staging and focused owner tests. This manifest
describes verified engineering coverage, explicit gaps, and deterministic
cross-interpreter normalized status digest. It is not an Audit or G0 verdict.
"""
from __future__ import annotations
import hashlib
import json
import os
import platform
from pathlib import Path

PINS = {
 "factory_e":"0ec35238de6cf48db07c5c977e1f0d04bc299f58",
 "factory_d":"a695e262da6787f752a13820f02dd00eef8ef1cd",
 "core_e":"3af5b66d2b381b853a6b5be32c38b3d3d02e1ea7",
 "core_d":"a86a590a5e2c32c18e03522f52896dbcf50c60ff",
 "scanner_e":"a2aa9c195095bcfe852fdc760e385ccb2acf3d5d",
 "scanner_d":"a91e370ae7e5197e9af71f8300eeaff4a7aff022",
 "discoverer_e":"149ca90c09b96abb45d3bc2839b657711c9826ac",
 "discoverer_base":"f2006c0e431690ccea8b0532095bf4f2a2dc88ba",
 "work235":"6acbcc7fc243b132f58170df4c6469bbf7f4eff8",
 "raw211":"7d97b09c0c6ee2650a61d523acb8d8c771a99c46",
 "core_f":"998e3bcca8ca6f1150964dfa9d94726fec96b846",
 "scanner_f":"aa9c23a620a8e10cdc7077c14d58401c26c54d48",
 "discoverer_f":"1cb70f1212283fe34117882d18e0501fc6409fe7",
}
# PASS is restricted to demonstrated bounded engineering subgate.
# PARTIAL / BLOCKED are NOT successful Package E completion.
GATES = {
 "G1":{"status":"PASS_SYNTHETIC_ENGINEERING_ONLY",
       "evidence":"Factory D same-source Core/Scanner Secretary ACK Lab isolated Paper"},
 "G2":{"status":"PASS_DISCOVERER_INTAKE_ONLY",
       "evidence":"independent checkpoint replay and Factory immutable research intake; Lab NOT_EVALUATED"},
 "G3":{"status":"HISTORICAL_SOURCE_BLOCKED",
       "evidence":"Core E original-source preflight; no authorized original ZIP or publisher issuance in public CI"},
 "G4":{"status":"PASS_BOUNDED_NEGATIVE_IDENTITIES",
       "evidence":"Factory D and E owner SHA and ledger adversarial tests"},
 "G5":{"status":"PARTIAL_RETROSPECTIVE_NON_PIT",
       "evidence":"Scanner E UTC and no-future boundary; historical available_at not independently attested"},
 "G6":{"status":"PASS_BOUNDED_DURABLE_LOCAL_SQLITE",
       "evidence":"Factory v1-v2 journaled migration, rollback/crash replay; Discoverer E durable checkpoint fresh read, idempotency and tamper denial; external custody not attested"},
 "G7":{"status":"PASS_SYNTHETIC_RULES_AND_HISTORICAL_WAIT",
       "evidence":"Factory D prefix AST and Scanner E no-SELECTED historical policy"},
 "G8":{"status":"PASS_BOUNDED_V1_V2_LAYOUT_MIGRATION",
       "evidence":"Factory E atomic additive index upgrade/rollback/replay and signed source parent metadata preservation"},
 "G9":{"status":"PASS_BOUNDED_SAFETY",
       "evidence":"TEST_ONLY no broker, Paper declined, zero orders/fills/positions, holdout unopened"},
 "G10":{"status":"PASS_BOUNDED_PINNED_COMPATIBILITY",
        "evidence":"exact Core E final source status, Scanner E historical policy proposal, Discoverer durable E, Factory E and frozen contracts with normalized parity; historical approval remains blocked"},
 "G11":{"status":"HISTORICAL_SOURCE_BLOCKED",
        "evidence":"genuine BTC vs synthetic AAA identity mismatch preserved; source missing WAIT"},
 "G12":{"status":"PASS_BOUNDED_RESEARCH_STORE_PERFORMANCE",
        "evidence":"12 strategies × 8 symbols × 4 candidate attempts: 96 experiments 384 attempts; public generated metadata only, 30s and 96MiB limits, cross-Python document digest parity; not indicator/backtest scalability"},
}
def canonical(obj):
    return json.dumps(obj, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False).encode()
def sha(obj):
    return hashlib.sha256(canonical(obj)).hexdigest()
def main():
    for name, value in PINS.items():
        if len(value)!=40 or not all(c in "0123456789abcdef" for c in value):
            raise SystemExit("INVALID_PIN "+name)
    normalized={
      "schema":"aql.integration.e.g1-g12-bounded-gate-manifest.v1",
      "pinned_owner_heads":PINS,
      "gates":GATES,
      "historical_source":"HISTORICAL_SOURCE_BLOCKED",
      "historical_pit":"NOT_ATTESTED",
      "source_custody":"NOT_IN_PUBLIC_RUNNER",
      "paper":"NOT_ACTIVATED",
      "trading_authority":"NONE",
      "orders_created":0, "actual_fills":None,
      "holdout":"SEALED_UNOPENED",
      "final_package_e":"CLOSED_ENGINEERING_WITH_EXTERNAL_HISTORICAL_BLOCKERS",
      "package_f":"OWNER_REPORTED_PRIVATE_F2_10_MONTHS_ADMITTED_F4_RECEIVER_READY_POLICY_ACK_NOT_VERIFIED",
      "package_f_policy":"OWNER_PROVISIONAL_CONDITIONAL_A_DORMANT",
      "package_f_f0_manifest":"OWNER_REPORTED_F2_RAW_WAREHOUSE_DUAL_QUERY_READBACK_10_MONTHS_NOT_IN_PUBLIC_RUNNER",
      "package_f_scanner_f3":"FINAL_ACTIVATION_REQUEST_PENDING_NOT_TRUSTED_APPROVAL_ZERO_SELECTED",
      "package_f_discoverer_f4":"WAIT_NOT_CONNECTED_OPTIONAL",
      "package_f_actual_original_source_backtest":"NOT_EXECUTED",
      "audit_verdict":"PENDING_FINAL_INDEPENDENT_DELTA_REVIEW",
    }
    report={"normalized":normalized,"normalized_sha256":sha(normalized),
            "python":platform.python_version(),
            "python_implementation":platform.python_implementation()}
    Path("e-gate-evidence.json").write_text(
        json.dumps(report,sort_keys=True,indent=2)+"\n",encoding="utf-8")
    print("ATLAS_E_NORMALIZED_SHA256="+report["normalized_sha256"])
    print("ATLAS_E_GATE_STATUS="+normalized["final_package_e"])
    for key,value in GATES.items():
        print(key+"="+value["status"])
if __name__=="__main__":
    main()
