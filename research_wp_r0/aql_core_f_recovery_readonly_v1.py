"""Core-owned F2_RECOVERY_EVIDENCE.v1: original-byte READ ONLY diagnostic.

This is NOT the original F2 report or an independent custodian, PIT,
SourceACK, StrategyApproval, ConsumerACK or any trading permission.
The recovery file format is opaque: pin its real bytes independently,
then distrust every mapping SHA until re-derived from existing source.
"""
from __future__ import annotations

from dataclasses import replace
import hashlib
import json
import os
from pathlib import Path
import sqlite3

from research_wp_r0.aql_archive_custody_bridge_v1 import (
    BarQuality, DataAvailabilityKind, HistoricalBar, HistoricalLibrary,
    SourceType, _load_checkpoint, decode, digest, validate_bars, verify_packet,
)
from research_wp_r0.aql_core_backbone_local_v1 import WAREHOUSE_SCHEMA, query_local
from research_wp_r0.aql_core_dual_query_identity_map_v1 import bind_dual_query_identities
from research_wp_r0.aql_core_f_private_f2_v1 import private_directory_gate
from research_wp_r0.aql_core_f_research_diagnostic_query_v1 import (
    ADMITTED_MONTHS, WIDTH_MS, _month_bounds,
)
from research_wp_r0.aql_core_research_query_seam_v1 import REQUEST_SCHEMA
from research_wp_r0.aql_native_price_custody_query_v1 import query_price_custody
from tools.raw_vault_offline.schema import RawObjectMeta, logical_identity_key

SCHEMA = "aql.core.f2-recovery-readonly-source.v1"
MAPPING_SCHEMA = "aql.integration.f2-recovery-evidence.v1"
# Owner-observed SHA256 of ACTUAL JSON FILE BYTES (PowerShell Get-FileHash).
EXPECTED_RECOVERY_BYTES_SHA256 = (
    "52b47d7d93f5966fffe41ae16cb21486fb14a0753a2821dccc35f4f09e4903d2"
)
# The producer's separate INTERNAL report identity; its canonical producer
# algorithm was NOT independently available. Never alias it to file-byte SHA.
EXPECTED_RECOVERY_INTERNAL_SHA256 = (
    "0428e7b02b7b57bded9906c49f956b76816c179cd8659d61e1c7f1af1df68220"
)
OWNER_REPORT_SCHEMA = "aql.owner-local.f2-recovery-evidence.v1"
OWNER_REPORT_DISPOSITION = "OWNER_LOCAL_DUAL_READBACK_PASS"
MONTH_FIELDS = frozenset((
    "month", "state", "bars", "source_sha256",
    "core_245_native_price_query_sha256", "core_253_local_query_sha256",
    "warehouse_receipt_sha256", "dual_query_map_sha256",
))
ROOT_FIELDS = frozenset((
    "schema", "source_class", "historical_pit", "trading_authority",
    "owner_f2_report_sha256", "entries",
))


def need(ok, code):
    if not ok:
        raise ValueError("CORE_F2_RECOVERY_" + code)


def hexsha(value):
    return type(value) is str and len(value) == 64 and all(
        x in "0123456789abcdef" for x in value)


def _existing(path, *, directory=False, limit=None):
    """No mkdir/resolve before symlink inspection, including every ancestor."""
    path = Path(path).absolute()
    need(not any(p.is_symlink() for p in (path, *path.parents)),
         "SYMLINK_PATH_DENIED")
    need(path.is_dir() if directory else path.is_file(), "EXISTING_PATH_REQUIRED")
    if not directory:
        need(path.stat().st_size > 0 and
             (limit is None or path.stat().st_size <= limit),
             "FILE_SIZE_LIMIT_OR_EMPTY")
    return path


def _json(path, limit):
    return json.loads(_existing(path, limit=limit).read_bytes())


def _tree_fingerprint(roots):
    """No-write assertion: detect added, removed or modified files/dirs.

    Snapshot metadata only, not private OHLCV; read atime is deliberately
    excluded. This check is supplementary to never invoking write APIs.
    """
    out = []
    for root in roots:
        root = _existing(root, directory=True)
        for base, dirs, files in os.walk(root, followlinks=False):
            base = Path(base)
            for name in sorted(dirs + files):
                p = base / name
                need(not p.is_symlink(), "SYMLINK_TREE_DENIED")
                st = p.stat()
                out.append((str(p.relative_to(root)), p.is_dir(),
                            st.st_size, st.st_mtime_ns, str(root)))
    return digest(out)



def owner_report_entry_mismatch_categories(report):
    """Return bounded PUBLIC-SAFE predicate classes; never return source values.

    Month labels are the only per-entry payload allowed. This is a read-only
    diagnostic, not an authority override. It does not change strict gates.
    """
    expected = set(ADMITTED_MONTHS)
    allowed = frozenset((
        "bars", "core245_native_query_sha256",
        "core253_local_query_sha256", "dataset_id", "manifest_sha256",
        "month", "source_sha256", "state",
    ))
    problems = {}
    def flag(category, month=None):
        slot = problems.setdefault(category, set())
        if type(month) is str and month in expected:
            slot.add(month)

    if type(report) is not dict:
        flag("ENTRY_FIELDS")
    else:
        entries = report.get("entries")
        if type(entries) is not list:
            flag("ENTRY_COUNT")
        else:
            if len(entries) != len(ADMITTED_MONTHS):
                flag("ENTRY_COUNT")
            seen = []
            total = 0
            numeric_bars = True
            for item in entries[:24]:
                if type(item) is not dict:
                    flag("ENTRY_FIELDS")
                    numeric_bars = False
                    continue
                month = item.get("month")
                known = month if type(month) is str and month in expected else None
                if set(item) != allowed:
                    flag("ENTRY_FIELDS", known)
                if known is None:
                    flag("MONTH_SET")
                else:
                    seen.append(known)
                    try:
                        start, end = _month_bounds(known)
                        if type(item.get("bars")) is not int or item["bars"] != (
                                end - start) // WIDTH_MS:
                            flag("MONTH_BAR_CENSUS", known)
                    except (ValueError, TypeError, KeyError):
                        flag("MONTH_BAR_CENSUS", known)
                    if item.get("dataset_id") != (
                            "BINANCE-SPOT-BTCUSDT-15M-" + known + "-F-v1"):
                        flag("DATASET_ID_PATTERN", known)
                if item.get("state") != "DUAL_READBACK_VERIFIED":
                    flag("STATE_LITERAL", known)
                if any(not hexsha(item.get(k)) for k in (
                    "source_sha256", "manifest_sha256",
                    "core245_native_query_sha256",
                    "core253_local_query_sha256",
                )):
                    flag("DIGEST_FORMAT", known)
                if type(item.get("bars")) is int:
                    total += item["bars"]
                else:
                    numeric_bars = False
            if len(entries) > 24:
                flag("ENTRY_COUNT")
            if set(seen) != expected or len(seen) != len(expected):
                flag("MONTH_SET")
                for missing in expected.difference(seen):
                    flag("MONTH_SET", missing)
                for month in set(seen):
                    if seen.count(month) > 1:
                        flag("MONTH_SET", month)
            if not numeric_bars or total != 29376 or len(entries) > 24:
                flag("TOTAL_BARS")
    return [
        {"category": category, "months": sorted(months)[:10]}
        for category, months in sorted(problems.items())
    ][:8]


def owner_report_safe_probe(path):
    """Read at most 5MB and return safe categories, never source values/errors."""
    try:
        original = _existing(path, limit=5_000_000).read_bytes()
        # Do not diagnose data with an unexpected raw file-byte SHA.
        if hashlib.sha256(original).hexdigest() != EXPECTED_RECOVERY_BYTES_SHA256:
            return {"status":"PRIVATE_WAIT","code":"OWNER_REPORT_FILE_PIN_MISMATCH",
                    "mismatches":[]}
        _owner_report_pins(original)
        return {"status":"ENTRY_PREDICATES_PASS",
                "code":"NONE","mismatches":[]}
    except ValueError as exc:
        # Only expose bounded static categories from verified report bytes.
        if str(exc) != "CORE_F2_RECOVERY_OWNER_REPORT_MONTH_CENSUS_OR_IDENTITY_DRIFT":
            return {"status":"PRIVATE_WAIT","code":"OWNER_REPORT_ROOT_OR_SCHEMA_BLOCKED",
                    "mismatches":[]}
        try:
            # File already passed SHA check. Parser duplicate/nonfinite gate
            # already passed in _owner_report_pins before entry predicates.
            report = json.loads(original)
            return {"status":"PRIVATE_WAIT",
                    "code":"OWNER_REPORT_MONTH_CENSUS_OR_IDENTITY_DRIFT",
                    "mismatches":owner_report_entry_mismatch_categories(report)}
        except (ValueError, TypeError, KeyError):
            return {"status":"PRIVATE_WAIT","code":"OWNER_REPORT_ROOT_OR_SCHEMA_BLOCKED",
                    "mismatches":[]}
    except (OSError, TypeError, OverflowError):
        return {"status":"PRIVATE_WAIT","code":"OWNER_REPORT_READ_DENIED",
                "mismatches":[]}


def _owner_report_pins(raw):
    """Require both real owner SHA pins and the observed producer report shape.

    Source rows are inside entries[]; verified_months is an INTEGER count.
    Producer's canonical internal digest algorithm remains unavailable; the
    byte-pinned internal digest field is checked but never re-computed here.
    """
    need(hashlib.sha256(raw).hexdigest() == EXPECTED_RECOVERY_BYTES_SHA256,
         "OPAQUE_RECOVERY_FILE_SHA_MISMATCH")

    def _pairs(items):
        data = {}
        for key, value in items:
            need(key not in data, "REPORT_DUPLICATE_KEY")
            data[key] = value
        return data

    def _reject_nonfinite(_):
        raise ValueError("CORE_F2_RECOVERY_REPORT_NONFINITE")

    try:
        report = json.loads(raw, object_pairs_hook=_pairs,
                            parse_constant=_reject_nonfinite)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("CORE_F2_RECOVERY_OWNER_REPORT_INVALID_JSON") from exc
    need(type(report) is dict and
         report.get("schema") == OWNER_REPORT_SCHEMA and
         report.get("recovery_sha256") == EXPECTED_RECOVERY_INTERNAL_SHA256 and
         report.get("disposition") == OWNER_REPORT_DISPOSITION and
         type(report.get("verified_months")) is int and
         report["verified_months"] == len(ADMITTED_MONTHS) and
         type(report.get("verified_bars")) is int and
         report["verified_bars"] == 29376,
         "OWNER_REPORT_SCHEMA_OR_INTERNAL_PIN_DRIFT")

    # The real owner's PowerShell dump established exact entry names; do not
    # silently interpret verified_months as an array or fill missing parents.
    fields = frozenset((
        "bars", "core245_native_query_sha256",
        "core253_local_query_sha256", "dataset_id", "manifest_sha256",
        "month", "source_sha256", "state",
    ))
    entries = report.get("entries")
    need(type(entries) is list and len(entries) == len(ADMITTED_MONTHS) and
         all(type(row) is dict and set(row) == fields for row in entries),
         "OWNER_REPORT_ENTRY_FIELDS_DRIFT")
    months = [row["month"] for row in entries]
    need(set(months) == set(ADMITTED_MONTHS) and
         len(months) == len(set(months)) and
         all(type(row["bars"]) is int and
             row["bars"] ==
             (_month_bounds(row["month"])[1]-_month_bounds(row["month"])[0]) //
             WIDTH_MS and
             row["dataset_id"] ==
             "BINANCE-SPOT-BTCUSDT-15M-" + row["month"] + "-F-v1" and
             row["state"] == "RAW_AND_DUAL_QUERY_READBACK" and
             all(hexsha(row[k]) for k in (
                 "source_sha256", "manifest_sha256",
                 "core245_native_query_sha256",
                 "core253_local_query_sha256",
             )) for row in entries) and
         sum(row["bars"] for row in entries) == 29376,
         "OWNER_REPORT_MONTH_CENSUS_OR_IDENTITY_DRIFT")

    # Explicit no-PIT/no-approval constraints from the observed report.
    need(report.get("historical_pit") == "NOT_ATTESTED" and
         report.get("trading_authority") == "NONE" and
         report.get("signed_f5_approval") in (None, False) and
         report.get("original_f2_report_restored") is False,
         "OWNER_REPORT_AUTHORITY_PROMOTION_DENIED")
    return report


def _verify_mapping(mapping):
    need(type(mapping) is dict and set(mapping) == ROOT_FIELDS and
         mapping["schema"] == MAPPING_SCHEMA and
         mapping["source_class"] == "OWNER_LOCAL_RECOVERY_NOT_ORIGINAL_F2" and
         mapping["historical_pit"] == "NOT_ATTESTED" and
         mapping["trading_authority"] == "NONE" and
         mapping["owner_f2_report_sha256"] is None,
         "MAPPING_SCOPE_OR_F2_IMPERSONATION")
    rows = mapping["entries"]
    need(type(rows) is list and len(rows) == 10 and
         all(type(row) is dict and set(row) == MONTH_FIELDS
             for row in rows) and
         {row["month"] for row in rows} == set(ADMITTED_MONTHS),
         "EXACT_TEN_ADMITTED_MONTHS_REQUIRED")
    need(all(row["state"] == "RAW_AND_DUAL_QUERY_READBACK" and
             type(row["bars"]) is int and
             row["bars"] == (_month_bounds(row["month"])[1] -
                             _month_bounds(row["month"])[0]) // WIDTH_MS and
             all(hexsha(row[k]) for k in MONTH_FIELDS if k.endswith("sha256"))
             for row in rows) and
         sum(row["bars"] for row in rows) == 29376,
         "MONTH_CENSUS_OR_SHA_INVALID")
    return {x["month"]: x for x in rows}


def _read_existing_month(warehouse_root, vault_root, month, untrusted):
    start, end = _month_bounds(month)
    cutoff = end + 1000  # retrospective F2 original query, NOT PIT
    need(type(untrusted) is dict and set(untrusted) == MONTH_FIELDS and
         untrusted.get("month") == month and
         untrusted.get("state") == "RAW_AND_DUAL_QUERY_READBACK" and
         untrusted.get("bars") == (end - start)//WIDTH_MS and
         all(hexsha(untrusted[k]) for k in MONTH_FIELDS if k.endswith("sha256")),
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
    need(warehouse_receipt["receipt_sha256"] ==
         untrusted["warehouse_receipt_sha256"],
         "RECOMPUTED_WAREHOUSE_RECEIPT_MISMATCH")

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
    need(dual["identity_map_sha256"] == untrusted["dual_query_map_sha256"],
         "RECOMPUTED_DUAL_MAP_DRIFT")
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


def read_recovery_diagnostic(warehouse_root, vault_root, recovery_file,
                             untrusted_mapping):
    """Public versioned 10-month source verifier; never accepts caller SHAs.

    The owner operator must separately authorize using its private paths.
    The opaque report *file bytes*, not any parsed/modeled report document,
    are pinned. All 10 mapping rows are independently source-backed.
    """
    recovery = _existing(recovery_file,limit=5_000_000)
    # Real file bytes and internal producer identity are two DIFFERENT pins.
    # Do not attempt to regenerate the producer's unknown digest algorithm.
    _owner_report_pins(recovery.read_bytes())
    entries = _verify_mapping(untrusted_mapping)
    results = {
        m:_read_existing_month(warehouse_root,vault_root,m,entries[m])
        for m in ADMITTED_MONTHS
    }
    need(sum(x["receipt"]["bar_count"] for x in results.values()) == 29376,
         "RECOMPUTED_TEN_MONTH_CENSUS")
    for result in results.values():
        body = {k:v for k,v in result["receipt"].items()
                if k != "receipt_sha256"}
        # Keep the cross-owner receipt field as the existing INTERNAL
        # recovery identifier. Add explicit raw-byte evidence without silently
        # changing the original field's semantics.
        body["recovery_file_sha256"] = EXPECTED_RECOVERY_INTERNAL_SHA256
        body["recovery_raw_bytes_sha256"] = EXPECTED_RECOVERY_BYTES_SHA256
        body["recovery_internal_canonical_recomputed"] = False
        body["opaque_recovery_file_pin_verified"] = True
        result["receipt"] = {**body,"receipt_sha256":digest(body)}
    return results
