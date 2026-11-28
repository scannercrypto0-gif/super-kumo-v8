"""Core #253 — offline, bounded historical RAW→indexed price→distribution backbone.

The ORIGINAL ZIP remains the source of record. Reuse Core #226 immutable
stager and optionally the existing #211 RawVault. No network, production
ingestion, paper authorization, external PIT claim or Factory rewrite.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import stat
import time

from research_wp_r0.aql_archive_custody_bridge_v1 import (
    OfflineBridgeStager, digest, raw_sha,
)
from research_wp_r0.aql_authenticated_historical_admission_v1 import (
    admit_original_bytes,
)
from research_wp_r0.aql_core_research_query_seam_v1 import REQUEST_SCHEMA
from research_wp_r0.aql_native_price_custody_query_v1 import query_price_custody
from research_wp_r0.aql_core_chronology_universe_evidence_v1 import (
    assess_chronology_universe,
)
from research_wp_r0.historical_library import HistoricalLibrary

WAREHOUSE_SCHEMA = "aql.core.local-history-warehouse.v1"
DISTRIBUTION_SCHEMA = "aql.core.local-history-distribution.v1"
HEX = re.compile(r"^[0-9a-f]{64}$")
IDENTITY = re.compile(r"^[A-Za-z0-9_.:-]{1,160}$")


class BackboneError(ValueError):
    pass


def require(ok, code):
    if not ok:
        raise BackboneError(code)


def _safe_root(root):
    root = Path(root).absolute()
    for p in (root, *root.parents):
        if p.exists() or p.is_symlink():
            require(not p.is_symlink(), "SYMLINK_ROOT_DENIED")
    return root


def _connect(root):
    location = _safe_root(root)
    location.mkdir(parents=True, exist_ok=True)
    db = location / "warehouse.sqlite"
    require(not db.is_symlink(), "SYMLINK_DB_DENIED")
    c = sqlite3.connect(db, timeout=15)
    c.execute("PRAGMA journal_mode=WAL")
    c.execute("PRAGMA synchronous=FULL")
    c.executescript("""
      CREATE TABLE IF NOT EXISTS generations (
       dataset_id TEXT NOT NULL, generation INTEGER NOT NULL,
       source_sha TEXT NOT NULL, manifest_sha TEXT NOT NULL,
       packet_sha TEXT NOT NULL, receipt_sha TEXT NOT NULL,
       correction_parent_sha TEXT, coverage TEXT NOT NULL,
       evidence_class TEXT NOT NULL,
       admission_json TEXT NOT NULL,
       PRIMARY KEY(dataset_id,generation)
      );
      CREATE TABLE IF NOT EXISTS price_bars (
       dataset_id TEXT NOT NULL, generation INTEGER NOT NULL,
       open_ms INTEGER NOT NULL, close_ms INTEGER NOT NULL,
       open_px REAL NOT NULL, high_px REAL NOT NULL,low_px REAL NOT NULL,
       close_px REAL NOT NULL, volume REAL NOT NULL,
       bar_sha TEXT NOT NULL, observation_lower_bound_ms INTEGER NOT NULL,
       PRIMARY KEY(dataset_id,generation,open_ms),
       FOREIGN KEY(dataset_id,generation)
         REFERENCES generations(dataset_id,generation)
      );
      CREATE INDEX IF NOT EXISTS idx_bars_time ON price_bars(dataset_id,open_ms,generation);
      CREATE TABLE IF NOT EXISTS distribution_outbox (
       message_id TEXT NOT NULL UNIQUE, payload_hash TEXT NOT NULL,
       lane TEXT NOT NULL, state TEXT NOT NULL, attempt_count INTEGER NOT NULL,
       delivery_json TEXT NOT NULL,
       ack_sha TEXT, priority INTEGER NOT NULL,
       next_attempt_ms INTEGER NOT NULL, last_error TEXT,
       created_sequence INTEGER PRIMARY KEY AUTOINCREMENT
      );
      CREATE TABLE IF NOT EXISTS distribution_events (
       event_seq INTEGER PRIMARY KEY AUTOINCREMENT,
       message_id TEXT NOT NULL, state TEXT NOT NULL,
       payload_sha256 TEXT NOT NULL, prev_sha256 TEXT,
       event_sha256 TEXT NOT NULL, event_json TEXT NOT NULL
      );
      CREATE INDEX IF NOT EXISTS idx_distribution_event_trace
       ON distribution_events(message_id,event_seq);
    """)
    c.execute("PRAGMA foreign_keys=ON")
    return c


def _sealed(value, key):
    require(type(value) is dict and
            type(value.get(key)) is str and
            HEX.fullmatch(value[key]) is not None,
            "SEAL_MISSING")
    require(digest({k:v for k,v in value.items() if k != key}) == value[key],
            "SEAL_MISMATCH")


def _vault_admit(vault, raw, pin, spec):
    """Pinned PR #211 RawVault: immutable per-generation content and lineage.

    RawVault logical identity is write-once, so each corrected generation gets
    a DISTINCT versioned logical identity. CorrectionLedger uses the stable
    base-family identity, preserving the parent chain without identity rewrite.
    The evidence is local bytes/integrity, NOT independent vendor publication.
    """
    if vault is None:
        return {"vault":"NOT_CONNECTED_CORE_STAGE_ONLY","sha256":raw_sha(raw),
                "correction_ledger":"NOT_CONNECTED"}
    from datetime import datetime, timezone
    from tools.raw_vault_offline.schema import RawObjectMeta,logical_identity_key
    from tools.raw_vault_offline.corrections import CorrectionLedger
    original={
        "vendor":"BINANCE_SPOT","instrument":spec["symbol"],
        "market":spec["market"],"interval":spec["interval"],
        "coverage_start_utc":datetime.fromtimestamp(
            spec["start_ms"]/1000, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "coverage_end_utc":datetime.fromtimestamp(
            spec["end_exclusive_ms"]/1000, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source_format":"ZIP_CSV","format_version":"BINANCE_NATIVE_MONTHLY_V1",
    }
    base_identity=logical_identity_key(**original)
    generation=spec["version"]-1
    identity={**original,"format_version":f"BINANCE_NATIVE_MONTHLY_V1_G{generation}"}
    lid=logical_identity_key(**identity)
    entries=vault.manifest_entries()
    existing=[i for i in entries if i["logical_identity_key"]==lid]
    require(len(existing)<=1,"VAULT_DUPLICATE_IDENTITY")
    if generation:
        require(any(i["content_sha256"]==spec["parent_source_sha256"]
                    and i["instrument"]==spec["symbol"] and
                    i["interval"]==spec["interval"] for i in entries),
                "VAULT_CORRECTION_PARENT_NOT_RETAINED")
    if existing:
        data=RawObjectMeta.from_dict(existing[0])
        require(data.content_sha256==pin["original_sha256"] and
                data.correction_generation==generation and
                data.parent_content_sha256==
                    (spec["parent_source_sha256"] or ""),
                "VAULT_VERSION_CONTENT_CONFLICT")
    else:
        data=RawObjectMeta(
            schema_version="raw_object.v1",content_sha256=raw_sha(raw),
            byte_length=len(raw),**identity,coverage_status="UNKNOWN",
            evidence_class="VENDOR_ARCHIVE",trust_status="UNVERIFIED",
            original_filename=pin["archive_name"],
            capture_provenance="OFFLINE_RETAINED_ORIGINAL_NOT_HISTORICAL_PIT",
            archive_member_path=pin["csv_member_name"],
            archive_member_sha256=pin["csv_member_sha256"],
            logical_identity_key=lid,
            admitted_at_utc=datetime.now(timezone.utc).isoformat().replace("+00:00","Z"),
            correction_generation=generation,
            parent_content_sha256=spec["parent_source_sha256"] or "",
        )
    admitted=vault.admit(raw,data)
    require(vault.read(admitted.content_sha256)==raw,"VAULT_READBACK_MISMATCH")
    ledger=CorrectionLedger(vault.root/"corrections.jsonl")
    if generation:
        chain=ledger.chain_for(base_identity)
        old=[record for record in chain if
             record.correction_generation==generation]
        require(len(old)<=1,"VAULT_CORRECTION_DUPLICATE")
        if old:
            rec=old[0]
            require(rec.content_sha256==admitted.content_sha256 and
                    rec.parent_sha256==spec["parent_source_sha256"] and
                    rec.reason==spec["correction_reason"],
                    "VAULT_CORRECTION_LEDGER_CONFLICT")
        else:
            rec=ledger.add_correction(
                new_content_sha256=admitted.content_sha256,
                parent_content_sha256=spec["parent_source_sha256"],
                logical_identity_key=base_identity,
                reason=spec["correction_reason"],
                evidence="LOCAL_ORIGINAL_BYTES_AND_PIN_NOT_ISSUER_PROOF",
            )
            require(rec.correction_generation==generation,
                    "VAULT_CORRECTION_GENERATION_DRIFT")
    return {"vault":"EXISTING_PINNED_RAW_VAULT",
            "sha256":admitted.content_sha256,
            "logical_identity_key":admitted.logical_identity_key,
            "correction_ledger":"PINNED_APPEND_ONLY" if generation
                                else "NO_CORRECTIONS",
            "base_family_identity":base_identity}


def admit_local_original(
    root, raw_zip, checksum_bytes, external_pin, spec, *,
    decision_cutoff_ms, vault=None,
):
    """ONE source object (<=4096 bars) committed to immutable Core and SQLite index.

    The index is a verified derived lookup, never RAW source authority. Crash
    retry: committed Bridge source replay + idempotent keyed SQLite insert.
    """
    require(type(raw_zip) is bytes and 0<len(raw_zip)<=8_000_000
            and type(checksum_bytes) is bytes and
            type(external_pin) is dict and
            external_pin.get("source_kind")=="BINANCE_KLINES_ZIP",
            "ORIGINAL_ZIP_AND_CHECKSUM_REQUIRED")
    require(type(spec) is dict and type(decision_cutoff_ms) is int,
            "INVALID_SOURCE_SCOPE")
    stage=OfflineBridgeStager(_safe_root(root)/"stage")
    lib=HistoricalLibrary()
    stage.replay_committed(lib)
    a=admit_original_bytes(
        raw_zip,external_pin,spec,stager=stage,library=lib,
        decision_cutoff_ms=decision_cutoff_ms,
        checksum_file_bytes=checksum_bytes,
    )
    require(a["coverage"] in ("COMPLETE","PARTIAL","UNKNOWN"),
            "CUSTODY_COVERAGE")
    q={
        "schema":REQUEST_SCHEMA,"dataset_id":spec["dataset_id"],
        "version":spec["version"],"start_ms":spec["start_ms"],
        "end_exclusive_ms":spec["end_exclusive_ms"],
        "decision_cutoff_ms":decision_cutoff_ms,
        "require_complete":False,"confirmed_only":False,
    }
    prices=query_price_custody(
        lib,q,expected_source_sha256=a["source_bytes_sha256"],
        expected_manifest_integrity_sha256=a["manifest_integrity_sha256"],
    )
    require(prices["status"]=="OK","PRICE_QUERY_UNAVAILABLE")
    # The original-byte Vault and Core stager are separate immutable stores;
    # errors never grant a false warehouse success.
    vault_receipt=_vault_admit(vault,raw_zip,external_pin,spec)
    con=_connect(root)
    try:
        con.execute("BEGIN IMMEDIATE")
        old=con.execute(
            "SELECT source_sha,manifest_sha,packet_sha FROM generations "
            "WHERE dataset_id=? AND generation=?",
            (spec["dataset_id"],spec["version"]),
        ).fetchone()
        current=(a["source_bytes_sha256"],a["manifest_integrity_sha256"],
                 a["packet_sha256"])
        require(old is None or old==current,"GENERATION_REWRITE_DENIED")
        if spec["version"]>1:
            parent=con.execute(
                "SELECT source_sha FROM generations WHERE dataset_id=? AND generation=?",
                (spec["dataset_id"],spec["version"]-1),
            ).fetchone()
            require(parent is not None and parent[0]==spec["parent_source_sha256"],
                    "GENERATION_CORRECTION_PARENT_MISMATCH")
        con.execute(
            "INSERT OR IGNORE INTO generations VALUES(?,?,?,?,?,?,?,?,?,?)",
            (spec["dataset_id"],spec["version"],a["source_bytes_sha256"],
             a["manifest_integrity_sha256"],a["packet_sha256"],
             a["custody_receipt_sha256"],spec["parent_source_sha256"],
             a["coverage"],a["underlying_availability_class"],
             json.dumps(a,sort_keys=True,separators=(",",":"))),
        )
        for bar in prices["bars"]:
            values=(spec["dataset_id"],spec["version"],
                    bar["bar_open_ms"],bar["bar_close_ms"],
                    bar["open"],bar["high"],bar["low"],bar["close"],
                    bar["volume"],bar["checksum"],
                    bar["observation_lower_bound_ms"])
            old_bar=con.execute(
                "SELECT close_ms,open_px,high_px,low_px,close_px,volume,bar_sha,observation_lower_bound_ms "
                "FROM price_bars WHERE dataset_id=? AND generation=? AND open_ms=?",
                (spec["dataset_id"],spec["version"],bar["bar_open_ms"]),
            ).fetchone()
            require(old_bar is None or old_bar==values[3:],
                    "DERIVED_PRICE_REWRITE_DENIED")
            con.execute(
                "INSERT OR IGNORE INTO price_bars VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                values,
            )
        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()
    body={
        "schema":WAREHOUSE_SCHEMA,"status":("OFFLINE_LOCAL_WAREHOUSE_COMMITTED" if vault is not None
                  else "OFFLINE_LOCAL_STAGE_ONLY"),
        "dataset_id":spec["dataset_id"],"version":spec["version"],
        "symbol":spec["symbol"],"market":spec["market"],
        "exchange":spec["exchange"],"interval":spec["interval"],
        "start_ms":spec["start_ms"],"end_exclusive_ms":spec["end_exclusive_ms"],
        "decision_cutoff_ms":decision_cutoff_ms,
        "test_only":spec["test_only"],
        "source_evidence_class":a["underlying_availability_class"],
        "source_zip_sha256":a["source_bytes_sha256"],
        "csv_member_sha256":a["native_csv_member_sha256"],
        "checksum_file_sha256":a["native_checksum_file_sha256"],
        "manifest_integrity_sha256":a["manifest_integrity_sha256"],
        "packet_sha256":a["packet_sha256"],
        "custody_receipt_sha256":a["custody_receipt_sha256"],
        "vault":vault_receipt,"coverage":a["coverage"],
        "bar_count":prices["available_bar_count"],
        "availability":"RETROSPECTIVE_NON_PIT",
        "historical_known_at":"NOT_ATTESTED",
        "universe":"NOT_ATTESTED","scientific_result":"INSUFFICIENT_EVIDENCE",
        "execution":"DISABLED",
    }
    return {**body,"receipt_sha256":digest(body)}


def query_local(root, dataset_id, version, start_ms, end_exclusive_ms,
                cutoff_ms, *, required_source_sha256, require_complete=True,
                sqlite_immutable=False):
    """Read only indexed derived price partition; no future-row repair."""
    require(type(dataset_id) is str and IDENTITY.fullmatch(dataset_id)
            and type(version) is int and version>0
            and all(type(v) is int and v>=0 for v in
                    (start_ms,end_exclusive_ms,cutoff_ms))
            and start_ms<end_exclusive_ms
            and type(required_source_sha256) is str and HEX.fullmatch(required_source_sha256)
            and type(require_complete) is bool
            and type(sqlite_immutable) is bool,
            "INVALID_HISTORICAL_QUERY")
    root=_safe_root(root)
    require((root/"warehouse.sqlite").is_file(),"WAREHOUSE_NOT_AVAILABLE")
    con=sqlite3.connect((root/"warehouse.sqlite").as_uri()+
                        ("?mode=ro&immutable=1" if sqlite_immutable else "?mode=ro"),
                        uri=True)
    try:
        g=con.execute(
            "SELECT source_sha,manifest_sha,coverage,admission_json FROM generations "
            "WHERE dataset_id=? AND generation=?",(dataset_id,version),
        ).fetchone()
        require(g is not None and g[0]==required_source_sha256,"SOURCE_PIN_NOT_FOUND")
        original=json.loads(g[3])
        _sealed(original,"manifest_record_sha256")
        require(original["source_bytes_sha256"]==g[0]
                and original["manifest_integrity_sha256"]==g[1],
                "WAREHOUSE_SOURCE_DRIFT")
        # Verify immutable source and Bridge packet independently of the index.
        if sqlite_immutable:
            # Bypass the legacy stager constructor, which calls mkdir even
            # on existing paths. Recovery has a strict NO-WRITES contract.
            stage=object.__new__(OfflineBridgeStager)
            stage.root=_safe_root(root/"stage")
            require(stage.root.is_dir(),"WAREHOUSE_STAGE_NOT_AVAILABLE")
        else:
            stage=OfflineBridgeStager(root/"stage")
        packet,raw=stage._load(original["packet_sha256"])
        require(packet["source_bytes_sha256"]==g[0]
                and raw_sha(raw)==g[0]
                and packet["spec"]["version"]==version
                and packet["spec"]["dataset_id"]==dataset_id,
                "WAREHOUSE_SOURCE_READBACK_DRIFT")
        from research_wp_r0.historical_library import _interval_to_ms
        step=_interval_to_ms(packet["spec"]["interval"])
        require(start_ms%step==0 and end_exclusive_ms%step==0
                and (end_exclusive_ms-start_ms)//step<=4096,
                "WAREHOUSE_QUERY_BOUNDS")
        found=con.execute(
            "SELECT open_ms,close_ms,open_px,high_px,low_px,close_px,volume,bar_sha,observation_lower_bound_ms "
            "FROM price_bars WHERE dataset_id=? AND generation=? AND open_ms>=? AND open_ms<? "
            "ORDER BY open_ms",(dataset_id,version,start_ms,end_exclusive_ms),
        ).fetchall()
        source={x["bar_open"]:x for x in packet["bars"]}
        bars=[]
        for item in found:
            t,close,op,hi,lo,cl,vol,hsh,eligible=item
            raw_bar=source.get(t)
            require(raw_bar is not None
                    and raw_bar["checksum"]==hsh
                    and raw_bar["bar_close"]==close
                    and (raw_bar["open"],raw_bar["high"],raw_bar["low"],
                         raw_bar["close"],raw_bar["volume"])==
                        (op,hi,lo,cl,vol)
                    and raw_bar["observation_cutoff_ms"]==eligible,
                    "WAREHOUSE_INDEX_TAMPER")
            if eligible<=cutoff_ms:
                bars.append({
                    "bar_open_ms":t,"bar_close_ms":close,"open":op,
                    "high":hi,"low":lo,"close":cl,"volume":vol,
                    "bar_checksum":hsh,"observation_lower_bound_ms":eligible,
                    "historical_known_at_ms":None,
                })
        expected=list(range(start_ms,end_exclusive_ms,step))
        got={x["bar_open_ms"] for x in bars}
        missing=[t for t in expected if t not in got]
        if require_complete:
            require(not missing,"WAREHOUSE_INCOMPLETE_OR_FUTURE")
        body={
            "schema":"aql.core.local-history-query.v1",
            "dataset_id":dataset_id,"version":version,
            "source_bytes_sha256":g[0],
            "manifest_integrity_sha256":g[1],
            "start_ms":start_ms,"end_exclusive_ms":end_exclusive_ms,
            "decision_cutoff_ms":cutoff_ms,
            "coverage":"COMPLETE" if not missing else "UNKNOWN" if not bars else "PARTIAL",
            "missing_bar_opens":missing,"required_bar_count":len(expected),
            "available_bar_count":len(bars),"bars":bars,
            "source_availability":"RETROSPECTIVE_NON_PIT",
            "historical_pit":"NOT_ATTESTED",
            "universe":"NOT_ATTESTED",
        }
        return {**body,"query_sha256":digest(body)}
    finally:
        con.close()
