"""Integration F2 private provenance collector; SOURCE-BACKED, READ ONLY.

Source-only fork of the exact Core #275 df8b956... _read_existing_month,
with two absent parent comparisons removed and independently recomputed.
Do NOT use this as original F2, a source-rights attestation or F5 approval.
Core's unmodified function is mandatory second verification.
"""
from __future__ import annotations

from dataclasses import replace
import hashlib
import json
import os
from pathlib import Path
import sqlite3

from research_wp_r0.aql_core_f_recovery_readonly_v1 import (
    need, hexsha, _existing, _json, _tree_fingerprint,
    private_directory_gate, ADMITTED_MONTHS, WIDTH_MS,
    _month_bounds, MONTH_FIELDS, WAREHOUSE_SCHEMA,
    decode, verify_packet, digest, RawObjectMeta, logical_identity_key,
    HistoricalBar, BarQuality, SourceType, DataAvailabilityKind,
    validate_bars, HistoricalLibrary, _load_checkpoint, query_local,
    query_price_custody, bind_dual_query_identities, REQUEST_SCHEMA,
)

def _derive_existing_month(warehouse_root, vault_root, month, untrusted):
    start, end = _month_bounds(month)
    cutoff = end + 1000  # retrospective F2 original query, NOT PIT
    need(type(untrusted) is dict and set(untrusted) == MONTH_FIELDS - {
             "warehouse_receipt_sha256", "dual_query_map_sha256"
         } and
         untrusted.get("month") == month and
         untrusted.get("state") == "RAW_AND_DUAL_QUERY_READBACK" and
         untrusted.get("bars") == (end - start)//WIDTH_MS and
         all(hexsha(untrusted[k]) for k in MONTH_FIELDS if k.endswith("sha256")
         and k not in {"warehouse_receipt_sha256", "dual_query_map_sha256"}),
         "UNTRUSTED_MONTH_FIELDS")
    warehouse_root = _existing(warehouse_root, directory=True)
    vault_root = _existing(vault_root, directory=True)
    private_directory_gate(warehouse_root)
    private_directory_gate(vault_root)
    before = _tree_fingerprint((warehouse_root, vault_root))
    db = _existing(warehouse_root/"warehouse.sqlite")
    stage_root = _existing(warehouse_root/"stage", directory=True)
    objects = _existing(vault_root/"objects", directory=True)
    _existing(vault_root/".staging", directory=True)
    index = _json(vault_root/"index.json", 15_000_000)
    manifest_path = _existing(vault_root/"manifest.jsonl", limit=40_000_000)

    source = untrusted["source_sha256"]
    dataset_id = "BINANCE-SPOT-BTCUSDT-15M-" + month + "-F-v1"
    # immutable=1 guarantees that query/PRAGMA cannot create -wal/-shm files.
    # If a live WAL is not checkpointed, the read MUST fail closed instead.
    con = sqlite3.connect(db.as_uri()+"?mode=ro&immutable=1", uri=True)
    try:
        row = con.execute(
            "SELECT source_sha, manifest_sha, packet_sha, receipt_sha,"
            " coverage, evidence_class, admission_json FROM generations "
            "WHERE dataset_id=? AND generation=1", (dataset_id,),
        ).fetchone()
        census = con.execute(
            "SELECT COUNT(*), MIN(open_ms), MAX(open_ms) FROM price_bars "
            "WHERE dataset_id=? AND generation=1", (dataset_id,),
        ).fetchone()
    finally:
        con.close()
    need(row is not None, "WAREHOUSE_GENERATION_NOT_FOUND")
    source_sql, manifest_sha, packet_sha, custody_sha, coverage, evidence, admission_json = row
    need(source_sql == source and all(hexsha(x) for x in
         (manifest_sha, packet_sha, custody_sha)) and coverage == "COMPLETE"
         and census == (untrusted["bars"], start, end - WIDTH_MS),
         "SQL_GENERATION_OR_FULL_MONTH_DRIFT")

    admission = json.loads(admission_json)
    seal = admission.get("manifest_record_sha256")
    need(hexsha(seal) and digest({
        k:v for k,v in admission.items() if k != "manifest_record_sha256"
    }) == seal and
         admission.get("source_bytes_sha256") == source and
         admission.get("manifest_integrity_sha256") == manifest_sha and
         admission.get("packet_sha256") == packet_sha and
         admission.get("custody_receipt_sha256") == custody_sha and
         admission.get("dataset_id") == dataset_id and
         admission.get("version") == 1 and
         admission.get("available_bar_count") == untrusted["bars"] and
         admission.get("coverage") == "COMPLETE" and
         admission.get("decision_cutoff_ms") == cutoff and
         admission.get("underlying_availability_class") == evidence and
         admission.get("authenticated_source") == "NOT_ATTESTED" and
         admission.get("confirmed_pit") == "NOT_ATTESTED" and
         admission.get("paper_live_trading") == "DISABLED",
         "SEALED_SQL_ADMISSION_DRIFT")

    folder = _existing(stage_root/packet_sha, directory=True)
    packet = decode(_existing(folder/"packet.json",limit=8_000_000).read_bytes())
    raw_stage = _existing(folder/"source.bin",limit=8_000_000).read_bytes()
    verify_packet(packet, raw_stage)
    spec = packet["spec"]
    need(packet.get("packet_sha256") == packet_sha and
         packet.get("source_bytes_sha256") == source and
         spec.get("dataset_id") == dataset_id and
         spec.get("version") == 1 and
         spec.get("start_ms") == start and
         spec.get("end_exclusive_ms") == end and
         spec.get("as_of_ms") == cutoff and
         spec.get("test_only") is False and
         spec.get("interval") == "15m" and
         _load_checkpoint(_existing(folder/"checkpoint.json",limit=200_000),
                          packet_sha, untrusted["bars"]) == untrusted["bars"],
         "COMMITTED_PACKET_OR_CHECKPOINT_DRIFT")
    stage_receipt = decode(_existing(folder/"receipt.json", limit=200_000).read_bytes())
    stage_sha = stage_receipt.get("receipt_sha256")
    need(hexsha(stage_sha) and
         digest({k:v for k,v in stage_receipt.items() if k != "receipt_sha256"}) ==
         stage_sha and
         stage_sha == custody_sha and
         stage_receipt.get("packet_sha256") == packet_sha and
         stage_receipt.get("source_bytes_sha256") == source and
         stage_receipt.get("manifest_integrity_sha256") == manifest_sha and
         stage_receipt.get("bar_count") == untrusted["bars"],
         "COMMITTED_STAGE_RECEIPT_DRIFT")

    # Verify direct RAW object, manifest and exact index association; no
    # RawVault constructor, no lockfile creation, no directory repair.
    vault_raw = _existing(objects/source[:2]/source[2:],limit=8_000_000).read_bytes()
    need(hashlib.sha256(vault_raw).hexdigest() == source and
         vault_raw == raw_stage, "RAW_BYTES_OR_STAGE_DRIFT")
    manifest = [json.loads(line) for line in
                manifest_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    matches = [x for x in manifest if x.get("content_sha256") == source]
    need(type(index) is dict and len(matches) == 1 and
         index.get(matches[0].get("logical_identity_key")) == source,
         "RAW_MANIFEST_INDEX_MISMATCH")
    meta = RawObjectMeta.from_dict(matches[0])
    need(meta.content_sha256 == source and
         meta.byte_length == len(vault_raw) and
         meta.instrument == "BTCUSDT" and
         meta.interval == "15m" and
         meta.correction_generation == 0 and
         meta.format_version == "BINANCE_NATIVE_MONTHLY_V1_G0",
         "RAW_ORIGINAL_METADATA_DRIFT")
    identity = {
        "vendor":"BINANCE_SPOT", "instrument":"BTCUSDT",
        "market":"SPOT", "interval":"15m",
        "coverage_start_utc": __import__("datetime").datetime.fromtimestamp(
            start/1000, __import__("datetime").timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "coverage_end_utc": __import__("datetime").datetime.fromtimestamp(
            end/1000, __import__("datetime").timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source_format":"ZIP_CSV", "format_version":"BINANCE_NATIVE_MONTHLY_V1",
    }
    base_family = logical_identity_key(**identity)
    g0_identity = logical_identity_key(**{
        **identity, "format_version":"BINANCE_NATIVE_MONTHLY_V1_G0",
    })
    need(meta.logical_identity_key == g0_identity and
         meta.vendor == identity["vendor"] and
         meta.market == identity["market"] and
         meta.coverage_start_utc == identity["coverage_start_utc"] and
         meta.coverage_end_utc == identity["coverage_end_utc"],
         "RAW_LOGICAL_IDENTITY_DRIFT")
    vault_receipt = {
        "vault":"EXISTING_PINNED_RAW_VAULT",
        "sha256":source, "logical_identity_key":g0_identity,
        "correction_ledger":"NO_CORRECTIONS",
        "base_family_identity":base_family,
    }
    body = {
        "schema":WAREHOUSE_SCHEMA,
        "status":"OFFLINE_LOCAL_WAREHOUSE_COMMITTED",
        "dataset_id":dataset_id, "version":1,
        "symbol":spec["symbol"], "market":spec["market"],
        "exchange":spec["exchange"], "interval":spec["interval"],
        "start_ms":start, "end_exclusive_ms":end,
        "decision_cutoff_ms":cutoff, "test_only":spec["test_only"],
        "source_evidence_class":admission["underlying_availability_class"],
        "source_zip_sha256":source,
        "csv_member_sha256":admission["native_csv_member_sha256"],
        "checksum_file_sha256":admission["native_checksum_file_sha256"],
        "manifest_integrity_sha256":manifest_sha,
        "packet_sha256":packet_sha,
        "custody_receipt_sha256":custody_sha,
        "vault":vault_receipt,
        "coverage":admission["coverage"],
        "bar_count":admission["available_bar_count"],
        "availability":"RETROSPECTIVE_NON_PIT",
        "historical_known_at":"NOT_ATTESTED",
        "universe":"NOT_ATTESTED", "scientific_result":"INSUFFICIENT_EVIDENCE",
        "execution":"DISABLED",
    }
    warehouse_receipt = {**body, "receipt_sha256":digest(body)}
    # Derivation has no caller-provided parent to compare with. This digest
    # was recomputed from the original immutable SQLite row, sealed committed
    # stage, and separately byte-checked RawVault object above.
    need(hexsha(warehouse_receipt["receipt_sha256"]), "DERIVED_WAREHOUSE_SHA")

    # Rehydrate already sealed source packet IN MEMORY only. Unlike
    # OfflineBridgeStager.commit() this has no implicit marker write path.
    bars = [HistoricalBar(**{
        **item, "quality":BarQuality(item["quality"]),
        "source":SourceType(item["source"]),
        "availability_kind":DataAvailabilityKind(item["availability_kind"]),
    }) for item in packet["bars"]]
    verified, regenerated = validate_bars(bars, spec["symbol"], spec["interval"])
    regenerated = replace(
        regenerated, dataset_id=dataset_id, version=1,
        exchange=spec["exchange"], market=spec["market"],
        source_label=spec["source_label"], created_at_ms=spec["as_of_ms"],
        parent_version=None, lineage_reason=None, source_hash=source)
    need(regenerated.manifest_integrity_hash == manifest_sha and
         stage_receipt.get("manifest_hash") == regenerated.manifest_hash,
         "REPLAYED_STAGE_MANIFEST_MISMATCH")
    lib = HistoricalLibrary()
    lib.register(dataset_id, verified, regenerated)
    local = query_local(
        warehouse_root,dataset_id,1,start,end,cutoff,
        required_source_sha256=source,require_complete=True,
        sqlite_immutable=True)
    native = query_price_custody(lib,{
        "schema":REQUEST_SCHEMA, "dataset_id":dataset_id, "version":1,
        "start_ms":start, "end_exclusive_ms":end,
        "decision_cutoff_ms":cutoff, "require_complete":False,
        "confirmed_only":False,
    }, expected_source_sha256=source,
       expected_manifest_integrity_sha256=manifest_sha)
    need(native.get("status") == "OK" and
         local.get("coverage") == native.get("coverage") == "COMPLETE" and
         native.get("price_query_sha256") ==
         untrusted["core_245_native_price_query_sha256"] and
         local.get("query_sha256") ==
         untrusted["core_253_local_query_sha256"] and
         len(native["bars"]) == len(local["bars"]) == untrusted["bars"] and
         all(a["bar_open_ms"] == b["bar_open_ms"] and
             a["bar_close_ms"] == b["bar_close_ms"] and
             a["checksum"] == b["bar_checksum"] and
             a["observation_lower_bound_ms"] == b["observation_lower_bound_ms"] and
             a["bar_close_ms"] < cutoff and
             a["historical_known_at_ms"] is None and
             b["historical_known_at_ms"] is None
             for a,b in zip(native["bars"],local["bars"])),
         "RECOMPUTED_NATIVE_LOCAL_QUERY_DRIFT")
    dual = bind_dual_query_identities(native,local,warehouse_receipt)
    # The independent #245/#253 queries have just been recomputed and the
    # native dual-query bind verifies both parent seals and original grids.
    need(hexsha(dual["identity_map_sha256"]), "DERIVED_DUAL_SHA")
    after = _tree_fingerprint((warehouse_root,vault_root))
    need(before == after, "SOURCE_TREE_MUTATED_DURING_READ")
    proof = {
        "schema":SCHEMA, "month":month, "dataset_id":dataset_id,
        "status":"SOURCE_BACKED_RECOVERY_READBACK_ONLY",
        "recovery_file_sha256":None,
        "opaque_recovery_file_pin_verified":False,
        "original_f2_report_sha256":None,
        "source_zip_sha256":source,
        "manifest_integrity_sha256":manifest_sha,
        "warehouse_receipt_sha256":warehouse_receipt["receipt_sha256"],
        "core245_native_query_sha256":native["price_query_sha256"],
        "core253_local_query_sha256":local["query_sha256"],
        "dual_map_sha256":dual["identity_map_sha256"],
        "bar_count":len(local["bars"]),
        "start_ms":start, "end_exclusive_ms":end,
        "decision_cutoff_ms":cutoff,
        "no_write_tree_fingerprint_sha256":before,
        "historical_pit":"NOT_ATTESTED",
        "source_ack_sha256":None,
        "strategy_approval_sha256":None,
        "factory_consumer_ack_sha256":None,
        "secretary_state":"NOT_ENQUEUED",
        "trading_authority":"NONE",
    }
    return {
        "receipt":{**proof,"receipt_sha256":digest(proof)},
        "native_bars":native["bars"], "local_bars":local["bars"],
    }


def _project_verified_recovery_entry(row):
    """Bridge report entry to the separate Core *mapping* state only.

    Recovery producer reports DUAL_READBACK_VERIFIED. Core's strict mapping
    verifier requires RAW_AND_DUAL_QUERY_READBACK after reconstruction of
    warehouse and dual-map source parents. The latter is NOT an assertion that
    the original F2 report was restored; the official Core source verifier
    must still independently replay the reconstructed ten-month mapping.
    """
    need(type(row) is dict and row.get("state") == "DUAL_READBACK_VERIFIED",
         "RECOVERY_ENTRY_STATE_DRIFT")
    return {
        "month": row["month"],
        "state": "RAW_AND_DUAL_QUERY_READBACK",
        "bars": row["bars"],
        "source_sha256": row["source_sha256"],
        "core_245_native_price_query_sha256":
            row["core245_native_query_sha256"],
        "core_253_local_query_sha256":
            row["core253_local_query_sha256"],
    }


def collect_recovery_source(warehouse_root, vault_root, recovery_file):
    """Derive two missing parents from ORIGINAL source bytes, never a claim.

    This module intentionally carries a reviewed source-only derivation
    fork of Core #275's _read_existing_month. The fork removes ONLY
    comparisons against the two parent identities absent from the producer
    report. It still parses and byte-verifies original ZIP, stage, RawVault,
    SQLite and both Core query domains before deriving the two digests.
    The official unmodified Core verifier then independently replays all 10
    rows, checking every derived digest; no authority is generated.
    """
    from research_wp_r0.aql_core_f_recovery_readonly_v1 import (
        _owner_report_pins, read_recovery_diagnostic,
    )
    from tools.atlas_f2_recovery_evidence_v1 import load_recovery_evidence
    recovery = _existing(recovery_file, limit=5_000_000)
    report = _owner_report_pins(recovery.read_bytes())
    source_rows = {row["month"]: row for row in report["entries"]}
    need(set(source_rows) == set(ADMITTED_MONTHS), "OWNER_TEN_MONTHS")
    rows = []
    for month in ADMITTED_MONTHS:
        row = source_rows[month]
        producer = _project_verified_recovery_entry(row)
        source = _derive_existing_month(
            warehouse_root, vault_root, month, producer)
        receipt = source["receipt"]
        need(receipt["source_zip_sha256"] == row["source_sha256"] and
             receipt["manifest_integrity_sha256"] == row["manifest_sha256"] and
             receipt["core245_native_query_sha256"] ==
                 row["core245_native_query_sha256"] and
             receipt["core253_local_query_sha256"] ==
                 row["core253_local_query_sha256"] and
             receipt["bar_count"] == row["bars"] and
             receipt["dataset_id"] == row["dataset_id"],
             "SOURCE_VS_OWNER_ROW_IDENTITY_DRIFT")
        rows.append({
            **producer,
            "warehouse_receipt_sha256": receipt["warehouse_receipt_sha256"],
            "dual_query_map_sha256": receipt["dual_map_sha256"],
        })
    mapping = {
        "schema": "aql.integration.f2-recovery-evidence.v1",
        "source_class": "OWNER_LOCAL_RECOVERY_NOT_ORIGINAL_F2",
        "historical_pit": "NOT_ATTESTED",
        "trading_authority": "NONE",
        "owner_f2_report_sha256": None,
        "entries": rows,
    }
    load_recovery_evidence(recovery_file, mapping)
    original = read_recovery_diagnostic(
        warehouse_root, vault_root, recovery_file, mapping)
    need(set(original) == set(ADMITTED_MONTHS) and
         sum(v["receipt"]["bar_count"] for v in original.values()) == 29376,
         "OFFICIAL_CORE_SECOND_READBACK_FAILED")
    for row in rows:
        sealed = original[row["month"]]["receipt"]
        need(sealed["warehouse_receipt_sha256"] ==
                 row["warehouse_receipt_sha256"] and
             sealed["dual_map_sha256"] == row["dual_query_map_sha256"] and
             sealed["source_zip_sha256"] == row["source_sha256"] and
             sealed["opaque_recovery_file_pin_verified"] is True and
             sealed["recovery_internal_canonical_recomputed"] is False and
             sealed["original_f2_report_sha256"] is None,
             "OFFICIAL_CORE_SOURCE_DERIVATION_DRIFT")
    return mapping, original
