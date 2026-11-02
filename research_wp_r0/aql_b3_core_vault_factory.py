"""B3 live software-seam integration of pinned Core F1, local Vault and Factory.

This invokes the *actual* RawVault.admit/read/manifest_entries from draft
Vault #211, then passes the retrieved Core fixture bytes to the real Factory
F1 consumer and the original market parent metadata to the Factory parent
bridge. No unmerged code is copied into Factory's committed tree: CI overlays
the pinned Core/Vault modules read-only. This is TEST_ONLY software integrity,
NOT independent issuer clock/custody, PIT or a historical strategy decision.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from .aql_w1_f1_prospective_consumer import project_core_verified_f1_slots
from .aql_w1_raw_parent_bridge import authenticated_parent_market_windows
from tools.raw_vault_offline.schema import (
    SCHEMA_VERSION, RawObjectMeta, TrustStatus, EvidenceClass, CoverageStatus,
    SourceFormat, logical_identity_key,
)
from tools.raw_vault_offline.vault import RawVault

CORE_SHA = "42005d09e3674420ddd8a761d40540c8e6509e8e79943d1f6a9821f692823b09"
B1_ARTIFACT_SHA = "265b7ade1be307bd2efafbd0a8438e6846c869df6205af717133d490e38aeb59"
B1_MARKET_REPORT_SHA = "1791109fcbc7a8370ca234fbd24d27bc37db1fc078a142c3b7c54ea9d55cdb11"
CORE_HEAD = "83d44ef23392b9ca9628d18d0f6fc909cd98e4ff"
FACTORY_BASE_HEAD = "ac7f160005672140a3254eb2ed82f4d586432b69"
VAULT_HEAD = "2ddfb2f4a6e145c6579820beb03e4d678594de21"
MONTHS = (2, 7)
HORIZONS = (14_400_000, 86_400_000, 259_200_000)


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical(obj) -> bytes:
    return (json.dumps(obj, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode()


def ensure(ok, code):
    if not ok:
        raise ValueError(code)


def meta_for(raw: bytes, *, vendor: str, source: str, coverage_start: str,
             coverage_end: str, evidence_class: EvidenceClass,
             trust_status: TrustStatus, source_format: SourceFormat,
             filename: str, member_path: str = "", member_sha: str = "") -> RawObjectMeta:
    """Faithful Vault schema, with local admission time (not independent evidence)."""
    return RawObjectMeta(
        schema_version=SCHEMA_VERSION,
        content_sha256=sha(raw), byte_length=len(raw),
        vendor=vendor, instrument="BTCUSDT", market=source,
        interval="15m", source_format=source_format, format_version="v1",
        coverage_start_utc=coverage_start, coverage_end_utc=coverage_end,
        coverage_status=CoverageStatus.FULL,
        evidence_class=evidence_class, trust_status=trust_status,
        original_filename=filename, capture_provenance="UNKNOWN_EXTERNAL_WITNESS",
        archive_member_path=member_path, archive_member_sha256=member_sha,
        logical_identity_key=logical_identity_key(
            vendor=vendor, instrument="BTCUSDT", market=source, interval="15m",
            coverage_start_utc=coverage_start, coverage_end_utc=coverage_end,
            source_format=source_format, format_version="v1",
        ),
        admitted_at_utc=datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
        correction_generation=0, parent_content_sha256="",
    )


def readback(vault: RawVault, raw: bytes, meta: RawObjectMeta) -> tuple[bytes, dict]:
    """Exercise real admit/readback, exactly-once local manifest and object digest."""
    vault.admit(raw, meta)
    persisted = vault.read(meta.content_sha256)
    ensure(persisted == raw and sha(persisted) == meta.content_sha256,
           "VAULT_READBACK_BYTES_MISMATCH")
    matching = [x for x in vault.manifest_entries()
                if x["logical_identity_key"] == meta.logical_identity_key]
    ensure(len(matching) == 1 and matching[0]["content_sha256"] == meta.content_sha256,
           "VAULT_MANIFEST_IDENTITY_OR_DIGEST_MISMATCH")
    return persisted, matching[0]


def source_from_accepted_b1(outer: zipfile.ZipFile, original: dict) -> tuple[bytes, bytes]:
    name = original["name"]
    raw = outer.read("b1-originals/" + name)
    vendor_checksum = outer.read("b1-originals/" + name + ".CHECKSUM")
    ensure(sha(raw) == original["archive_sha256"]
           and len(raw) == original["archive_bytes"], "ORIGINAL_MARKET_PARENT_DIGEST_DRIFT")
    ensure(sha(vendor_checksum) == original["checksum_sha256"]
           and vendor_checksum.decode("ascii").strip().split()
              == [original["archive_sha256"], name], "MARKET_VENDOR_CHECKSUM_DRIFT")
    # B1 already fully audited. No monthly/full-year candle or outcome re-analysis here.
    return raw, vendor_checksum


def verify_binding_fails_closed(plan: dict, source_meta: dict) -> dict:
    """B2 Core fixture cutoff/source cannot be retroactively made into 2024 PIT."""
    cutoff = plan["decision_cutoff_ms"]
    coverage_start = int(datetime.fromisoformat(
        source_meta["coverage_start_utc"].replace("Z", "+00:00")).timestamp() * 1000)
    source_pin_matches = plan["source_bytes_sha256"] == source_meta["content_sha256"]
    source_available_at_cutoff = coverage_start <= cutoff
    ensure(not (source_pin_matches and source_available_at_cutoff),
           "UNEXPECTED_AUTHENTIC_ORIGINAL_SOURCE_MATCH")
    return {
        "status": "BLOCKED_SOURCE_VINTAGE_AND_CUTOFF_MISMATCH",
        "core_cutoff_ms": cutoff,
        "original_parent_sha256": source_meta["content_sha256"],
        "original_parent_coverage_start_ms": coverage_start,
        "original_core_source_pin_sha256": plan["source_bytes_sha256"],
        "source_pin_matches": source_pin_matches,
        "parent_coverage_starts_before_cutoff": source_available_at_cutoff,
        "original_core_identity_modified": False,
    }


def integrate(core_bytes: bytes, b1_bytes: bytes, vault_root: Path) -> dict:
    ensure(sha(core_bytes) == CORE_SHA, "CORE_INPUT_DRIFT")
    ensure(sha(b1_bytes) == B1_ARTIFACT_SHA, "ORIGINAL_MARKET_B1_ARTIFACT_DRIFT")
    core = json.loads(core_bytes)
    ensure(core.get("schema_version") == "aql.b2-core-factory-integrity-input.v1"
           and core.get("evidence_class") == "TEST_ONLY_CONTROLLED_SYSTEM_INPUT"
           and core.get("original_pit_verified") is False
           and core.get("live_f3_connected") is False,
           "UNSAFE_CORE_SOURCE_CLASS")
    n = core["n"]
    plans = core["schedule"]
    ensure(n == 2 and len(plans) == n and core["expected_2n"] == 2*n
           and core["expected_6n"] == 6*n, "CORE_DENOMINATOR")
    vault = RawVault(vault_root)
    # Actual Core F1 candidates are admitted to the exact Vault v1 software API.
    # This is a test-only F1 evidence object, NOT the market parent source.
    persisted_f1 = []
    core_admissions = []
    seen_ids = set()
    for i, plan in enumerate(plans):
        pair = plan["pair_id"]
        ensure(pair not in seen_ids, "DUPLICATE_CORE_PAIR")
        seen_ids.add(pair)
        originals = sorted(
            (x for x in core["original_candidates_test_only"] if x["pair_id"] == pair),
            key=lambda x: x["arm"],
        )
        ensure(len(originals) == 2 and [x["arm"] for x in originals] == ["BASE", "SHADOW"],
               "ORIGINAL_CORE_ARM_MISSING_OR_DUPLICATED")
        raw_f1 = canonical(originals)
        meta = meta_for(
            raw_f1, vendor="AQL_CORE_B2_TEST_PAIR_"+str(i+1), source="TEST_ONLY_F1",
            coverage_start="1970-01-01T00:00:00Z",
            coverage_end="1970-01-01T00:15:00Z",
            evidence_class=EvidenceClass.FIXTURE_SYNTHETIC,
            trust_status=TrustStatus.UNVERIFIED, source_format=SourceFormat.JSON_LINES,
            filename="core-b2-f1-test-only-"+str(i+1)+".jsonl",
        )
        recovered, manifest = readback(vault, raw_f1, meta)
        from_readback = json.loads(recovered)
        ensure(from_readback == originals
               and all(x["pair_id"] == pair for x in from_readback),
               "F1_VAULT_READBACK_IDENTITY_DRIFT")
        persisted_f1.extend(from_readback)
        core_admissions.append({
            "pair_id": pair, "actual_raw_vault_admit": "PASS",
            "actual_raw_vault_read": "PASS",
            "actual_manifest_match": "PASS",
            "object_sha256": sha(recovered),
            "logical_identity_key": manifest["logical_identity_key"],
            "manifest_evidence_class": manifest["evidence_class"],
            "independent_external_witness": False,
        })
    # The other admission is a REAL original market archive, unmodified, but it
    # is not falsely asserted to be the source behind 1970-era Core fixtures.
    parent_by_pair = {}
    manifest_by_pair = {}
    original_admissions = []
    with zipfile.ZipFile(io.BytesIO(b1_bytes)) as outer:
        market_report_bytes = outer.read("b1-replay/report.json")
        ensure(sha(market_report_bytes) == B1_MARKET_REPORT_SHA,
               "ACCEPTED_B1_MARKET_REPORT_DRIFT")
        report = json.loads(market_report_bytes)
        original_map = {x["name"]: x for x in report["originals"]}
        for i, (month, plan) in enumerate(zip(MONTHS, plans)):
            name = f"BTCUSDT-15m-2024-{month:02}.zip"
            item = original_map[name]
            parent, _ = source_from_accepted_b1(outer, item)
            start = ("2024-02-01T00:00:00Z" if month == 2
                     else "2024-07-01T00:00:00Z")
            end = ("2024-03-01T00:00:00Z" if month == 2
                   else "2024-08-01T00:00:00Z")
            meta = meta_for(
                parent, vendor="BINANCE_VISION_ORIGINAL", source="SPOT",
                coverage_start=start, coverage_end=end,
                evidence_class=EvidenceClass.VENDOR_ARCHIVE,
                trust_status=TrustStatus.VERIFIED, source_format=SourceFormat.ZIP_CSV,
                filename=name, member_path=name.replace(".zip", ".csv"),
                member_sha=item["member_sha256"],
            )
            recovered, manifest = readback(vault, parent, meta)
            parent_by_pair[plan["pair_id"]] = recovered
            manifest_by_pair[plan["pair_id"]] = manifest
            source_binding = verify_binding_fails_closed(plan, manifest)
            original_admissions.append({
                "pair_id": plan["pair_id"],
                "archive_name": name,
                "vault_admit_readback": "PASS",
                "vault_manifest_sha_bound": "PASS",
                "vendor_archive_checksum": "PASS_SAME_VENDOR_NOT_INDEPENDENT",
                "content_sha256": meta.content_sha256,
                "logical_identity_key": meta.logical_identity_key,
                "original_core_source_binding": source_binding,
            })
    # Real Factory market parent bridge: no externally trusted verifier, no
    # derived provenance; therefore NO market authority is produced.
    windows, market_verifier = authenticated_parent_market_windows(
        plans, parent_by_pair, manifest_by_pair,
        derived_bars_by_pair={}, derived_evidence_by_pair={},
        verify_parent_manifest=None, verify_derivation=None,
        verify_external_receipt=None,
    )
    ensure(not windows and market_verifier({}) is False,
           "FORGED_PARENT_WITNESS_PROMOTION")
    # Real Factory F1 consumer consumes *only* F1 recovered from actual Vault.
    consumer = project_core_verified_f1_slots(
        plans, persisted_f1, windows,
        indicator_registry=core["indicator_registry"],
        proof_verifier=None, verify_market=market_verifier,
    )
    ensure(consumer["scheduled_total"] == n
           and consumer["arm_slots"] == 2*n
           and consumer["outcome_rows"] == 6*n, "FACTORY_POST_VAULT_N_2N_6N")
    actual = {(x["pair_id"], x["arm"], x["horizon_ms"]) for x in consumer["outcomes"]}
    expected = {(p["pair_id"], arm, h)
                for p in plans for arm in ("BASE", "SHADOW") for h in HORIZONS}
    ensure(len(actual) == 6*n and actual == expected,
           "FACTORY_POST_VAULT_LOST_DUPLICATE_OR_MISASSIGNED_ARM")
    ensure(all(x["capture_status"] == "UNVERIFIED"
               and x["coverage_status"] == "UNKNOWN"
               and x["max_favorable"] is None
               and x["max_adverse"] is None
               and x["no_fill_or_pnl_inference"] is True
               for x in consumer["outcomes"]), "UNAUTHORIZED_PIT_MARKET_PROMOTION")
    entries = vault.manifest_entries()
    ensure(len(entries) == 2*n
           and len({x["logical_identity_key"] for x in entries}) == 2*n,
           "VAULT_MANIFEST_ENTRY_DUPLICATE_OR_MISSING")
    manifest_raw = (vault.root / "manifest.jsonl").read_bytes()
    return {
        "schema": "aql.b3.local-core-vault-factory-integrity.v1",
        "result": "PASS_LOCAL_SOFTWARE_SEAM_WITH_UNVERIFIED_MARKET_BOUNDARY",
        "scope": "TEST_ONLY_LOCAL_VAULT_AND_FACTORY_CONSUMER",
        "pinned_input": {"core_sha256": CORE_SHA,
                         "original_b1_artifact_sha256": B1_ARTIFACT_SHA,
                         "core_pr_head": CORE_HEAD,
                         "factory_base_head": FACTORY_BASE_HEAD,
                         "vault_pr_head": VAULT_HEAD},
        "actual_vault_software": {
            "objects_admitted": len(entries),
            "manifest_entries": len(entries),
            "manifest_bytes_sha256": sha(manifest_raw),
            "core_F1_objects": core_admissions,
            "original_market_parent_objects": original_admissions,
            "manifest_independently_witnessed": False,
            "readback_originality_not_external_attestation": True,
        },
        "post_vault_factory_consumer": {
            "N": n, "expected_2N": 2*n, "observed_2N": consumer["arm_slots"],
            "expected_6N": 6*n, "observed_6N": consumer["outcome_rows"],
            "capture_status": "UNVERIFIED_ALL_FOUR",
            "market_coverage": "UNKNOWN_ALL_TWELVE",
            "unverified_test_direction_authorized": False,
            "core_input_recovered_from_actual_vault_readback": True,
        },
        "seams": {
            "Core_TEST_ONLY_F1_bytes_to_actual_Vault_admit_readback": "PASS_LOCAL_SOFTWARE",
            "B1_original_RAW_market_parent_to_actual_Vault_admit_readback": "PASS_LOCAL_SOFTWARE",
            "Vault_readback_TEST_ONLY_F1_to_actual_Factory_consumer": "PASS_UNVERIFIED_2N_6N",
            "Vault_parent_manifest_to_Factory_bridge_without_external_witness": "BLOCKED_FAIL_CLOSED",
            "Core_original_F1_source_to_2024_market_parent": "NOT_CONNECTED_SOURCE_CUTOFF_MISMATCH",
            "external_issuer_custody_clock_proof": "BLOCKED_EXTERNAL_EVIDENCE",
            "original_F1_to_monitor_snapshots": "NOT_CONNECTED",
            "real_prospective_producer_to_F3": "NOT_CONNECTED",
            "TP_SL_fills_strategy_efficacy": "NOT_TESTED",
        },
        "no_historical_F1_or_operational_PIT_proof": True,
        "no_g0_or_deployment": True,
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--core", type=Path, required=True)
    ap.add_argument("--b1-artifact", type=Path, required=True)
    ap.add_argument("--vault-root", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()
    ensure(not args.out.exists(), "REPORT_IMMUTABLE_REFUSE_OVERWRITE")
    result = integrate(args.core.read_bytes(), args.b1_artifact.read_bytes(), args.vault_root)
    output = canonical(result)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_bytes(output)
    print("B3_RESULT=" + result["result"])
    print("B3_N_2N_6N=" + str(result["post_vault_factory_consumer"]["N"]) + "/"
          + str(result["post_vault_factory_consumer"]["observed_2N"]) + "/"
          + str(result["post_vault_factory_consumer"]["observed_6N"]))
    print("B3_REPORT_SHA256=" + sha(output))


if __name__ == "__main__":
    main()
