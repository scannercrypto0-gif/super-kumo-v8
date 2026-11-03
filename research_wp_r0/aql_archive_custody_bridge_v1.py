"""AQL-HISTORICAL-ARCHIVE-CUSTODY-BRIDGE-001: isolated OFFLINE bridge only.

No live ingestion, market collection, production custody or scientific acceptance.
The durable source is an independently verified sealed archive snapshot / RAW vault
object, NOT the in-memory HistoricalLibrary destination. Derived availability
is RETROSPECTIVE even if archive ingest timestamps or vault admission are known.
"""
from __future__ import annotations

import csv
from dataclasses import asdict, replace
from datetime import datetime, timezone
from hashlib import sha256
from io import StringIO
import json
import math
import os
from pathlib import Path
import re
import tempfile

from research_wp_r0.historical_library import (
    BarQuality, DataAvailabilityKind, HistoricalBar, HistoricalDataError,
    HistoricalLibrary, SourceType, _interval_to_ms, validate_bars,
)

PACKET_SCHEMA = "aql.archive-custody.offline-packet.v1"
RECEIPT_SCHEMA = "aql.archive-custody.local-registration.v1"
MAX_SOURCE_BYTES = 8_000_000
MAX_BARS = 4096
HEX = re.compile(r"^[0-9a-f]{64}$")
IDENTITY = re.compile(r"^[A-Za-z0-9_.:-]{1,160}$")


class BridgeError(ValueError):
    pass


def require(condition, code):
    if not condition:
        raise BridgeError(code)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False).encode("utf-8")


def digest(value):
    return sha256(canonical(value)).hexdigest()


def raw_sha(raw):
    return sha256(raw).hexdigest()


def decode(raw):
    require(type(raw) is bytes and 0 < len(raw) <= MAX_SOURCE_BYTES,
            "SOURCE_BYTES_REQUIRED_OR_TOO_LARGE")
    def pairs(items):
        obj = {}
        for key, value in items:
            require(key not in obj, "DUPLICATE_JSON_KEY")
            obj[key] = value
        return obj
    def reject(_):
        raise BridgeError("NONFINITE_JSON")
    try:
        return json.loads(raw, object_pairs_hook=pairs, parse_constant=reject)
    except (UnicodeError, ValueError) as exc:
        raise BridgeError("INVALID_SOURCE_JSON") from exc


def validate_spec(spec):
    require(type(spec) is dict and set(spec) == {
        "dataset_id", "version", "symbol", "interval", "exchange", "market",
        "source_label", "start_ms", "end_exclusive_ms", "as_of_ms",
        "parent_source_sha256", "correction_reason", "test_only",
    }, "SPEC_FIELDS")
    for key in ("dataset_id", "symbol", "interval", "exchange", "market", "source_label"):
        require(type(spec[key]) is str and bool(IDENTITY.fullmatch(spec[key])),
                "SPEC_IDENTITY_" + key.upper())
    for key in ("version", "start_ms", "end_exclusive_ms", "as_of_ms"):
        require(type(spec[key]) is int and spec[key] >= 0, "SPEC_TIME_OR_VERSION")
    require(spec["version"] >= 1 and spec["start_ms"] < spec["end_exclusive_ms"]
            and spec["as_of_ms"] >= spec["end_exclusive_ms"], "SPEC_TEMPORAL")
    require(type(spec["test_only"]) is bool, "SPEC_TEST_FLAG")
    require(spec["version"] == 1 and spec["parent_source_sha256"] is None
            and spec["correction_reason"] is None or
            spec["version"] > 1 and type(spec["parent_source_sha256"]) is str
            and bool(HEX.fullmatch(spec["parent_source_sha256"]))
            and type(spec["correction_reason"]) is str
            and bool(spec["correction_reason"].strip()), "CORRECTION_LINEAGE_REQUIRED")
    width = _interval_to_ms(spec["interval"])
    require(width > 0 and spec["start_ms"] % width == 0
            and spec["end_exclusive_ms"] % width == 0
            and (spec["end_exclusive_ms"]-spec["start_ms"])//width <= MAX_BARS,
            "UNBOUNDED_OR_MISALIGNED_RANGE")
    return width


def _bar_record(spec, opened, closed, values, *, receipt_ms):
    width = _interval_to_ms(spec["interval"])
    require(type(opened) is int and type(closed) is int
            and closed == opened + width-1 and opened % width == 0,
            "INVALID_BAR_GRID")
    try:
        o, h, l, c, v = [float(x) for x in values]
    except (ValueError, TypeError, OverflowError) as exc:
        raise BridgeError("INVALID_OHLCV") from exc
    require(all(math.isfinite(x) for x in (o,h,l,c,v)) and
            l > 0 and l <= o <= h and l <= c <= h and v >= 0,
            "INVALID_OHLCV")
    require(receipt_ms is None or (type(receipt_ms) is int and
            closed + 1 <= receipt_ms <= spec["as_of_ms"]),
            "FUTURE_OR_INCONSISTENT_RECEIPT")
    lower_bound = max(closed+1, receipt_ms or 0)
    return HistoricalBar(
        symbol=spec["symbol"], interval=spec["interval"], bar_open=opened,
        bar_close=closed, open=o, high=h, low=l, close=c, volume=v,
        quality=BarQuality.FINAL, source=(SourceType.SYNTHETIC if spec["test_only"]
                                        else SourceType.ARCHIVE),
        source_label=spec["source_label"],
        observation_cutoff_ms=lower_bound, ingest_time_ms=receipt_ms,
        availability_kind=DataAvailabilityKind.RETROSPECTIVE,
    )


def _archive_records(raw, spec, meta):
    source = decode(raw)
    require(meta.get("kind") == "SEALED_ARCHIVE_QUERY"
            and type(meta.get("inventory_hash")) is str
            and bool(HEX.fullmatch(meta["inventory_hash"])), "ARCHIVE_SOURCE_PIN")
    require(source.get("schema") == "aql.offline-archive-query.v1"
            and source.get("inventory_hash") == meta["inventory_hash"]
            and source.get("retrospective_only") is True
            and source.get("pit_eligibility") == "NOT_ATTESTED"
            and source.get("independent_custody_verified") is False
            and source.get("coverage") == "ARCHIVED_RECORDS_ONLY_NOT_FULL_MARKET",
            "ARCHIVE_EVIDENCE_BOUNDARY")
    selection = source.get("selection")
    require(type(selection) is dict and
            selection.get("symbol") == spec["symbol"] and
            selection.get("interval") == spec["interval"] and
            selection.get("start_open_ms") == spec["start_ms"] and
            selection.get("end_open_ms_exclusive") == spec["end_exclusive_ms"],
            "ARCHIVE_SCOPE_MISMATCH")
    records = source.get("records")
    require(type(records) is list and 0 < len(records) <= MAX_BARS
            and source.get("count") == len(records)
            and source.get("record_content_hash") == digest(records),
            "ARCHIVE_RECORD_DIGEST")
    from src.aql.models.bar import MarketBar
    converted, origin, ids, seqs, journal_ids = [], [], set(), set(), set()
    for record in records:
        require(type(record) is dict, "INVALID_ARCHIVE_RECORD")
        obj = dict(record)
        seal = obj.pop("envelope_hash", None)
        require(type(seal) is str and bool(HEX.fullmatch(seal))
                and digest(obj) == seal
                and record.get("schema") == "aql.market-archive.v1",
                "ARCHIVE_ENVELOPE_TAMPER")
        times = record.get("times")
        require(type(times) is dict and
                record.get("availability_kind") ==
                    "DERIVED_LOWER_BOUND_NOT_CONFIRMED" and
                times.get("available_ms") is None and
                times.get("fsync_completed_ms") is None,
                "ARCHIVE_AVAILABILITY_UPGRADE")
        try:
            market_bar = MarketBar.from_dict(record["bar"])
        except (ValueError, TypeError, KeyError) as exc:
            raise BridgeError("ARCHIVE_BAR_SCHEMA") from exc
        require(market_bar.is_final is True
                and record.get("record_id") == market_bar.stable_key()
                and market_bar.checksum in (None, "", market_bar.compute_checksum())
                and record.get("journal_content_checksum") == market_bar.compute_checksum()
                and times.get("market_close_ms") == market_bar.bar_close
                and times.get("receipt_ms") == market_bar.ingested_at
                and times.get("ingest_ms") == market_bar.ingested_at
                and times.get("availability_lower_bound_ms") ==
                    max(market_bar.bar_close+1, market_bar.ingested_at),
                "ARCHIVE_BAR_SOURCE_PROVENANCE")
        seq = record.get("source_seq")
        require(type(seq) is int and seq >= 1
                and type(record.get("journal_id")) is str
                and bool(record["journal_id"])
                and seq not in seqs
                and record["record_id"] not in ids,
                "DUPLICATE_OR_INVALID_SOURCE_ID")
        ids.add(record["record_id"]); seqs.add(seq); journal_ids.add(record["journal_id"])
        require(market_bar.symbol == spec["symbol"] and
                market_bar.interval == spec["interval"], "ARCHIVE_CROSS_SOURCE")
        converted.append(_bar_record(
            spec, market_bar.bar_open, market_bar.bar_close,
            (market_bar.open, market_bar.high, market_bar.low,
             market_bar.close, market_bar.volume),
            receipt_ms=market_bar.ingested_at))
        origin.append({"record_id":record["record_id"],"source_seq":seq,
                       "journal_id":record["journal_id"],
                       "original_bar_checksum":market_bar.compute_checksum(),
                       "archive_envelope_hash":seal,
                       "original_source_label":market_bar.source,
                       "source_receipt_ms":market_bar.ingested_at,
                       "source_commit_recorded_ms":market_bar.committed_at})
    require(len(journal_ids) == 1, "MIXED_ARCHIVE_JOURNAL_IDENTITIES")
    return converted, origin


def _vault_records(raw, spec, meta):
    require(meta.get("kind") == "RAW_VAULT_OBJECT"
            and type(meta.get("object")) is dict, "VAULT_METADATA_REQUIRED")
    item = meta["object"]
    require(item.get("schema_version") == "raw_object.v1"
            and item.get("content_sha256") == raw_sha(raw)
            and item.get("byte_length") == len(raw)
            and item.get("source_format") == "RAW_CSV"
            and item.get("instrument") == spec["symbol"]
            and item.get("interval") == spec["interval"]
            and item.get("market") == spec["market"]
            and type(item.get("logical_identity_key")) is str
            and bool(HEX.fullmatch(item["logical_identity_key"])),
            "VAULT_OBJECT_IDENTITY_OR_FORMAT")
    identity_fields = ("vendor", "instrument", "market", "interval",
                       "coverage_start_utc", "coverage_end_utc",
                       "source_format", "format_version")
    require(all(type(item.get(k)) is str and bool(item[k]) for k in identity_fields)
            and item["logical_identity_key"] ==
                digest({k: item[k] for k in identity_fields}),
            "VAULT_LOGICAL_IDENTITY_MISMATCH")
    require(item.get("evidence_class") in
            ("DIRECT_DOWNLOAD","VENDOR_ARCHIVE","MANUAL_EXPORT",
             "FIXTURE_SYNTHETIC","UNKNOWN"), "VAULT_EVIDENCE_CLASS")
    require(spec["test_only"] or item["evidence_class"] != "FIXTURE_SYNTHETIC",
            "SYNTHETIC_NOT_REAL_SOURCE")
    require(item.get("trust_status") in ("VERIFIED","UNVERIFIED","UNKNOWN"),
            "VAULT_TRUST_CLASS")
    generation = item.get("correction_generation")
    require(type(generation) is int and generation >= 0
            and spec["version"] == generation + 1
            and (generation == 0 and item.get("parent_content_sha256") in (None,"")
                 or generation > 0 and
                 item.get("parent_content_sha256") == spec["parent_source_sha256"]),
            "VAULT_CORRECTION_LINEAGE")
    def utc_ms(value):
        require(type(value) is str and value.endswith("Z"), "VAULT_UTC_REQUIRED")
        try:
            d = datetime.fromisoformat(value.replace("Z","+00:00"))
            return int(d.timestamp()*1000)
        except ValueError as exc:
            raise BridgeError("VAULT_UTC_REQUIRED") from exc
    require(utc_ms(item.get("coverage_start_utc")) == spec["start_ms"]
            and utc_ms(item.get("coverage_end_utc")) == spec["end_exclusive_ms"],
            "VAULT_COVERAGE_SCOPE")
    require(utc_ms(item.get("admitted_at_utc")) <= spec["as_of_ms"],
            "FUTURE_VAULT_ADMISSION")
    try:
        body = raw.decode("utf-8-sig")
    except UnicodeError as exc:
        raise BridgeError("VAULT_CSV_ENCODING") from exc
    converted, origin = [], []
    for i, parts in enumerate(csv.reader(StringIO(body))):
        require(len(parts) == 7, "VAULT_CSV_COLUMNS")
        try:
            opened, closed = int(parts[0]), int(parts[1])
        except (ValueError, TypeError) as exc:
            raise BridgeError("VAULT_CSV_TIME") from exc
        converted.append(_bar_record(spec, opened, closed, parts[2:], receipt_ms=None))
        origin.append({"source_csv_line":i+1,"original_object_sha256":raw_sha(raw),
                       "bar_historical_receipt_ms":None,
                       "object_admitted_at_utc":item.get("admitted_at_utc")})
    require(len(converted) <= MAX_BARS, "UNBOUNDED_VAULT_ROWS")
    return converted, origin


def _build_packet(raw, spec, meta):
    width = validate_spec(spec)
    require(type(raw) is bytes and 0 < len(raw) <= MAX_SOURCE_BYTES
            and type(meta) is dict, "SOURCE_BYTES_REQUIRED")
    if meta.get("kind") == "SEALED_ARCHIVE_QUERY":
        bars, origin = _archive_records(raw,spec,meta)
    elif meta.get("kind") == "RAW_VAULT_OBJECT":
        bars, origin = _vault_records(raw,spec,meta)
    else:
        raise BridgeError("UNSUPPORTED_SOURCE_ADAPTER")
    expected = (spec["end_exclusive_ms"]-spec["start_ms"])//width
    require(len(bars) == expected
            and bars[0].bar_open == spec["start_ms"]
            and bars[-1].bar_open+width == spec["end_exclusive_ms"],
            "INCOMPLETE_COHORT_COVERAGE")
    try:
        verified, _ = validate_bars(bars, spec["symbol"],spec["interval"])
    except (HistoricalDataError, ValueError) as exc:
        raise BridgeError("INVALID_SOURCE_BARS") from exc
    require(verified == bars and len(origin) == len(bars), "SOURCE_ORDER_DRIFT")
    packed = []
    for bar in bars:
        d = asdict(bar)
        for enum_name in ("quality","source","availability_kind"):
            d[enum_name] = getattr(bar, enum_name).value
        packed.append(d)
    body = {"schema":PACKET_SCHEMA,
            "status":"OFFLINE_STAGED_NOT_INTEGRATED",
            "spec":dict(spec),"source_meta":dict(meta),
            "source_bytes_sha256":raw_sha(raw),
            "source_byte_length":len(raw),
            "bars":packed,"origin_lineage":origin,
            "bar_checksums_sha256":digest([b.checksum for b in bars]),
            "dataset_content_sha256":digest(packed),
            "availability_class":"RETROSPECTIVE_NOT_CONFIRMED",
            "evidence_class":"SYNTHETIC_TEST" if spec["test_only"]
                             else "RETROSPECTIVE_NON_PIT",
            "source_confidence":"SOURCE_PIN_AND_LOCAL_INTEGRITY_ONLY",
            "coverage":"COMPLETE_VALIDATED_GRID",
            "external_custody_verified":False}
    return {**body,"packet_sha256":digest(body)}


def export_archive_query(raw, *, expected_source_sha256, expected_inventory_hash,
                         spec):
    require(type(expected_source_sha256) is str
            and bool(HEX.fullmatch(expected_source_sha256))
            and raw_sha(raw) == expected_source_sha256,
            "ARCHIVE_SOURCE_BYTES_SHA_MISMATCH")
    return _build_packet(raw,spec,{"kind":"SEALED_ARCHIVE_QUERY",
                                   "inventory_hash":expected_inventory_hash})


def export_existing_archive_backup(root, *, expected_inventory_hash,
                                   spec, max_rows=MAX_BARS):
    """Uses the EXISTING fully verified sealed-backup read-only adapter."""
    from src.aql.archive.offline import snapshot
    raw = snapshot(root,expected_digest=expected_inventory_hash,
                   symbol=spec["symbol"],interval=spec["interval"],
                   start_ms=spec["start_ms"],end_ms=spec["end_exclusive_ms"],
                   max_rows=max_rows)
    return export_archive_query(raw,expected_source_sha256=raw_sha(raw),
                                expected_inventory_hash=expected_inventory_hash,
                                spec=spec), raw


def export_vault_csv(raw, *, expected_source_sha256, object_metadata, spec):
    require(type(expected_source_sha256) is str and
            bool(HEX.fullmatch(expected_source_sha256))
            and raw_sha(raw) == expected_source_sha256,
            "VAULT_SOURCE_BYTES_SHA_MISMATCH")
    return _build_packet(raw,spec,{"kind":"RAW_VAULT_OBJECT",
                                   "object":dict(object_metadata)})


def export_existing_raw_vault(vault, *, content_sha256, spec):
    """Duck-typed PR#211 RawVault.read/manifest_entries; never imports its branch."""
    require(type(content_sha256) is str and bool(HEX.fullmatch(content_sha256)),
            "VAULT_SOURCE_PIN")
    entries = [e for e in vault.manifest_entries()
               if e.get("content_sha256") == content_sha256]
    require(len(entries) == 1, "VAULT_MANIFEST_AMBIGUOUS")
    raw = vault.read(content_sha256)
    return export_vault_csv(raw,expected_source_sha256=content_sha256,
                            object_metadata=entries[0],spec=spec), raw


def verify_packet(packet, source_raw):
    require(type(packet) is dict and packet.get("schema") == PACKET_SCHEMA,
            "PACKET_SCHEMA")
    actual = packet.get("packet_sha256")
    require(type(actual) is str and bool(HEX.fullmatch(actual))
            and digest({k:v for k,v in packet.items() if k!="packet_sha256"})==actual,
            "PACKET_DIGEST_MISMATCH")
    require(packet.get("source_bytes_sha256")==raw_sha(source_raw),
            "PACKET_SOURCE_SHA_MISMATCH")
    reproduced = _build_packet(source_raw,packet.get("spec"),packet.get("source_meta"))
    require(reproduced==packet,"PACKET_SOURCE_REPLAY_MISMATCH")
    return packet


def _safe_dir(path):
    path = Path(path).absolute()
    for item in (path, *path.parents):
        if item.is_symlink():
            raise BridgeError("SYMLINK_PATH_DENIED")
    return path


def _write_immutable(path, data):
    path = _safe_dir(path)
    if path.exists():
        require(path.is_file() and path.read_bytes()==data,
                "IMMUTABLE_STAGE_CONFLICT")
        return
    fd,name=tempfile.mkstemp(prefix=".bridge-stage-",dir=str(path.parent))
    try:
        with os.fdopen(fd,"wb") as handle:
            handle.write(data);handle.flush();os.fsync(handle.fileno())
        try:
            os.link(name,path)
        except FileExistsError:
            require(path.read_bytes()==data,"IMMUTABLE_STAGE_CONFLICT")
    finally:
        os.unlink(name)


def _atomic_checkpoint(path, body):
    path=_safe_dir(path)
    raw=canonical({**body,"checkpoint_sha256":digest(body)})
    fd,name=tempfile.mkstemp(prefix=".bridge-checkpoint-",dir=str(path.parent))
    try:
        with os.fdopen(fd,"wb") as handle:
            handle.write(raw);handle.flush();os.fsync(handle.fileno())
        os.replace(name,path)
    finally:
        if os.path.exists(name):os.unlink(name)


def _load_checkpoint(path, key, total):
    data=decode(path.read_bytes())
    seal=data.pop("checkpoint_sha256",None)
    require(seal==digest(data) and data.get("schema")=="aql.bridge.checkpoint.v1"
            and data.get("packet_sha256")==key
            and type(data.get("verified_rows")) is int
            and 0 <= data["verified_rows"] <= total,
            "INVALID_STAGE_CHECKPOINT")
    return data["verified_rows"]


class OfflineBridgeStager:
    """Durable local staging+resume, then ONE validated in-memory registration.

    HistoricalLibrary itself is NOT durable custody. On process restart use a
    new library and explicit replay_committed(), never claim automatic recovery.
    """
    def __init__(self,root):
        self.root=_safe_dir(root)
        self.root.mkdir(parents=True,exist_ok=True)

    def _folder(self,key):
        require(type(key) is str and bool(HEX.fullmatch(key)), "BAD_STAGE_KEY")
        return _safe_dir(self.root/key)

    def stage(self,packet,source_raw):
        verify_packet(packet,source_raw)
        key=packet["packet_sha256"]
        folder=self._folder(key)
        folder.mkdir(exist_ok=True)
        _write_immutable(folder/"source.bin",source_raw)
        _write_immutable(folder/"packet.json",canonical(packet))
        checkpoint=folder/"checkpoint.json"
        if not checkpoint.exists():
            _atomic_checkpoint(checkpoint,{"schema":"aql.bridge.checkpoint.v1",
                                          "packet_sha256":key,"verified_rows":0})
        _load_checkpoint(checkpoint,key,len(packet["bars"]))
        return key

    def _load(self,key):
        folder=self._folder(key)
        require(folder.is_dir(),"STAGE_NOT_FOUND")
        packet=decode((folder/"packet.json").read_bytes())
        source_raw=(folder/"source.bin").read_bytes()
        verify_packet(packet,source_raw)
        require(packet["packet_sha256"]==key,"STAGE_KEY_MISMATCH")
        return packet,source_raw

    def advance(self,key,*,batch_size=64):
        require(type(batch_size) is int and 1<=batch_size<=256,
                "INVALID_BATCH_SIZE")
        packet,_=self._load(key)
        folder=self._folder(key)
        progress=_load_checkpoint(folder/"checkpoint.json",key,len(packet["bars"]))
        next_count=min(len(packet["bars"]),progress+batch_size)
        for row in packet["bars"][progress:next_count]:
            require(type(row.get("checksum")) is str
                    and bool(HEX.fullmatch(row["checksum"])),
                    "UNSEALED_SOURCE_BAR")
        _atomic_checkpoint(folder/"checkpoint.json",{
            "schema":"aql.bridge.checkpoint.v1",
            "packet_sha256":key,"verified_rows":next_count})
        return next_count,len(packet["bars"])

    def commit(self,key,library:HistoricalLibrary):
        packet,_=self._load(key)
        folder=self._folder(key)
        require(_load_checkpoint(folder/"checkpoint.json",key,len(packet["bars"]))==
                len(packet["bars"]),"INCOMPLETE_BATCH_CHECKPOINT")
        require(isinstance(library,HistoricalLibrary),"HISTORICAL_LIBRARY_REQUIRED")
        spec=packet["spec"]
        from research_wp_r0.historical_library import HistoricalBar as HB
        bars=[]
        for row in packet["bars"]:
            bar=HB(**{**row,"quality":BarQuality(row["quality"]),
                      "source":SourceType(row["source"]),
                      "availability_kind":DataAvailabilityKind(row["availability_kind"])})
            require(bar.checksum==row["checksum"],"REGISTERED_BAR_HASH_DRIFT")
            bars.append(bar)
        verified,manifest=validate_bars(bars,spec["symbol"],spec["interval"])
        version=spec["version"]
        try:
            latest=library.latest_version(spec["dataset_id"])
        except HistoricalDataError:
            latest=0
        if version>1:
            require(latest>=version-1,"MISSING_CORRECTION_PARENT")
            parent=library.get_manifest(spec["dataset_id"],version-1)
            require(parent.source_hash==spec["parent_source_sha256"],
                    "CORRECTION_PARENT_SOURCE_MISMATCH")
        manifest=replace(manifest,dataset_id=spec["dataset_id"],
                         version=version,exchange=spec["exchange"],
                         market=spec["market"],source_label=spec["source_label"],
                         created_at_ms=spec["as_of_ms"],
                         parent_version=version-1 if version>1 else None,
                         lineage_reason=spec["correction_reason"],
                         source_hash=packet["source_bytes_sha256"])
        if latest>=version:
            existing=library.get_manifest(spec["dataset_id"],version)
            require(existing.manifest_integrity_hash==
                    manifest.manifest_integrity_hash,
                    "EXISTING_VERSION_CONTENT_CONFLICT")
            # Avoid a false idempotent claim when a caller tampered an in-memory bar.
            current=library._datasets[spec["dataset_id"]][version][0]
            require([b.checksum for b in current]==[b.checksum for b in verified]
                    and all(b.verify_checksum() for b in current),
                    "EXISTING_BAR_CONTENT_CONFLICT")
            status="IDEMPOTENT_ALREADY_REGISTERED"
        else:
            require(latest==version-1,"VERSION_GAP_OR_REWRITE")
            library.register(spec["dataset_id"],verified,manifest)
            status="REGISTERED_IN_MEMORY_ONLY"
        receipt={"schema":RECEIPT_SCHEMA,"packet_sha256":key,
                 "source_bytes_sha256":packet["source_bytes_sha256"],
                 "dataset_id":spec["dataset_id"],"version":version,
                 "manifest_integrity_sha256":manifest.manifest_integrity_hash,
                 "manifest_hash":manifest.manifest_hash,
                 "bar_count":len(verified),"status":status,
                 "destination":"HISTORICAL_LIBRARY_IN_MEMORY_ONLY",
                 "independent_custody_verified":False,
                 "production_integration":"NOT_ACTIVATED",
                 "evidence_class":packet["evidence_class"]}
        receipt={**receipt,"receipt_sha256":digest(receipt)}
        # Immutable committed marker must not change upon a retry.
        marker=folder/"receipt.json"
        if marker.exists():
            prior=decode(marker.read_bytes())
            require(prior["packet_sha256"]==key
                    and prior["manifest_integrity_sha256"]==manifest.manifest_integrity_hash,
                    "EXISTING_RECEIPT_CONFLICT")
            return prior
        _write_immutable(marker,canonical(receipt))
        return receipt

    def replay_committed(self,library):
        """Explicit startup rehydration; validates each retained source again."""
        found=[]
        for folder in sorted(self.root.iterdir()):
            if not folder.is_dir() or not HEX.fullmatch(folder.name):
                continue
            if (folder/"receipt.json").is_file():
                packet,_=self._load(folder.name)
                found.append((packet["spec"]["dataset_id"],packet["spec"]["version"],folder.name))
        receipts=[]
        for _,_,key in sorted(found):
            receipts.append(self.commit(key,library))
        return receipts


def custody_range(library,dataset_id,start_ms,end_exclusive_ms,
                  decision_cutoff_ms,*,version=None,
                  require_complete=True,confirmed_only=False):
    """Bounded read-only range; [start,end) and strict known-at cutoff.

    confirmed_only rejects any retrospective source; no PIT upgrades.
    """
    require(isinstance(library,HistoricalLibrary),"HISTORICAL_LIBRARY_REQUIRED")
    for t in (start_ms,end_exclusive_ms,decision_cutoff_ms):
        require(type(t) is int and t>=0,"INVALID_QUERY_TIME")
    require(start_ms<end_exclusive_ms and type(require_complete) is bool
            and type(confirmed_only) is bool,"INVALID_QUERY")
    manifest=library.get_manifest(dataset_id,version)
    width=_interval_to_ms(manifest.interval)
    require(start_ms%width==0 and end_exclusive_ms%width==0
            and (end_exclusive_ms-start_ms)//width<=MAX_BARS,
            "INVALID_QUERY_GRID")
    if confirmed_only:
        from research_wp_r0.historical_library import CustodyAccessor
        accessor=CustodyAccessor(library)
        try:
            bars=accessor.range_query(dataset_id,start_ms,end_exclusive_ms-width,
                                      decision_cutoff_ms,version=version,
                                      require_complete=False)
        except HistoricalDataError:
            bars=[]
    else:
        try:
            bars=library.range_query(dataset_id,start_ms,end_exclusive_ms-width,
                                     decision_cutoff_ms,version=version,
                                     require_complete=False)
        except HistoricalDataError:
            bars=[]
    expected=list(range(start_ms,end_exclusive_ms,width))
    got={b.bar_open for b in bars}
    missing=[t for t in expected if t not in got]
    if require_complete:
        require(not missing,"INCOMPLETE_OR_FUTURE_CUSTODY_RANGE")
    return {"schema":"aql.bridge.custody-range.v1",
            "dataset_id":dataset_id,
            "version":manifest.version if version is None else version,
            "manifest_integrity_sha256":manifest.manifest_integrity_hash,
            "source_bytes_sha256":manifest.source_hash,
            "decision_cutoff_ms":decision_cutoff_ms,
            "status":"COMPLETE" if not missing else "UNKNOWN" if not bars else "PARTIAL",
            "available_bar_count":len(bars),"required_bar_count":len(expected),
            "missing_bar_opens":missing,
            "availability_class":"CONFIRMED_ONLY" if confirmed_only
                                 else "SYNTHETIC_TEST" if any(b.source == SourceType.SYNTHETIC for b in bars)
                                 else "RETROSPECTIVE_NOT_PIT",
            "source_confidence":"LOCAL_CHECKSUM_AND_PIN_ONLY",
            "bars":[{"bar_open":b.bar_open,"bar_close":b.bar_close,
                     "checksum":b.checksum,
                     "observation_cutoff_ms":b.observation_cutoff_ms,
                     "availability_kind":b.availability_kind.value}
                    for b in bars],
            "research_evaluation":"NOT_PERFORMED"}
