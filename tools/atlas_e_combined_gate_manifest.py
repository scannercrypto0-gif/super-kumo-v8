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
 "factory_e":"ccc563f8a838d3ed07c0cf6725aca5ead9b9209e",
 "factory_d":"a695e262da6787f752a13820f02dd00eef8ef1cd",
 "core_e":"3c23ba606c94a2d9e7a95d2dce122adbc7d9e88e",
 "core_d":"a86a590a5e2c32c18e03522f52896dbcf50c60ff",
 "scanner_e":"58fc02ba4a0c5bb0a64d5187b400c0620a49f389",
 "scanner_d":"a91e370ae7e5197e9af71f8300eeaff4a7aff022",
 "discoverer_e":"79adda0b06d4299cde5dec3f14de985014cd330d",
 "discoverer_base":"f2006c0e431690ccea8b0532095bf4f2a2dc88ba",
 "work235":"6acbcc7fc243b132f58170df4c6469bbf7f4eff8",
 "raw211":"7d97b09c0c6ee2650a61d523acb8d8c771a99c46",
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
 "G6":{"status":"PARTIAL_DURABILITY",
       "evidence":"Factory SQLite replay/idempotency; Discoverer in-memory ledger has no durable crash recovery"},
 "G7":{"status":"PASS_SYNTHETIC_RULES_AND_HISTORICAL_WAIT",
       "evidence":"Factory D prefix AST and Scanner E no-SELECTED historical policy"},
 "G8":{"status":"PARTIAL_IMMUTABLE_STORE",
       "evidence":"Factory E schema v1 immutable store and comparison; no schema migration exercised"},
 "G9":{"status":"PASS_BOUNDED_SAFETY",
       "evidence":"TEST_ONLY no broker, Paper declined, zero orders/fills/positions, holdout unopened"},
 "G10":{"status":"PARTIAL_PINNED_COMPATIBILITY",
        "evidence":"exact owner HEADs and normalized manifest parity; no full historical contract"},
 "G11":{"status":"HISTORICAL_SOURCE_BLOCKED",
        "evidence":"genuine BTC vs synthetic AAA identity mismatch preserved; source missing WAIT"},
 "G12":{"status":"NOT_VERIFIED_BOUNDED_PERFORMANCE",
        "evidence":"no realistic multi-strategy multi-symbol benchmark performed"},
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
      "final_package_e":"NOT_COMPLETE_HISTORICAL_AND_G6_G8_G12_BLOCKERS",
      "audit_verdict":"NOT_REQUESTED_UNTIL_FULL_OWNER_EVIDENCE",
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
