"""Opt-in, bounded producer-side status receipts for isolated MCP staging.

Never scans the warehouse, DB, WAL, active scheduler, or data archive.
The caller passes already-committed, sanitized in-memory evidence at a safe point.
This is NOT a FullHistory completeness or trading authorization decision.
"""
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import tempfile

MAX_REPORT_BYTES = 8192
HEX = re.compile(r"[0-9a-f]{64}\Z")
TOKEN = re.compile(r"[A-Za-z0-9_.-]{1,90}\Z")


def _require(ok, reason):
    if not ok:
        raise ValueError(reason)


def _safe_path(path):
    p = Path(path).absolute()
    for member in (p, *p.parents):
        if member.exists() or member.is_symlink():
            bits = member.lstat()
            _require(not stat.S_ISLNK(bits.st_mode)
                     and not (getattr(bits, "st_file_attributes", 0) & 0x400),
                     "PRODUCER_REPORT_REPARSE_DENIED")
    return p


def _hex_or_none(value):
    return value is None or (type(value) is str and HEX.fullmatch(value))


def _daily_metadata(source, imported):
    if source is None and imported is None:
        return
    source_fields = {"schema", "key", "source_zip_sha256", "source_zip_bytes", "checksum_sha256",
        "rows", "first_open_ms", "last_open_ms", "observed_ms", "source_class", "historical_known_at_ms",
        "publisher_integrity", "independent_origin_attestation", "trading_authority", "member_sha256",
        "member_bytes", "period_start_ms", "period_end_ms", "timestamp_unit", "receipt_sha256"}
    import_fields = {"status", "key", "source_sha256", "source_rows", "inserted_rows", "duplicate_rows",
        "repaired_internal_minutes", "conflicts", "source_class", "trading_authority", "registry_action",
        "observed_ms", "before", "policy_ref"}
    _require(type(source) is dict and type(imported) is dict and set(source) <= source_fields
             and set(imported) <= import_fields, "PRODUCER_REPORT_NATIVE_METADATA_FIELDS")
    for value in (source, imported):
        for key, item in value.items():
            if key.endswith("sha256"):
                _require(type(item) is str and HEX.fullmatch(item), "PRODUCER_REPORT_NATIVE_METADATA_DIGEST")
            elif key == "key":
                _require(type(item) is str and re.fullmatch(
                    r"data/spot/daily/klines/BTCUSDT/1m/BTCUSDT-1m-[0-9]{4}-[0-9]{2}-[0-9]{2}\.zip", item),
                    "PRODUCER_REPORT_NATIVE_METADATA_KEY")
            elif type(item) is dict:
                _require(key == "before" and set(item) == {"missing_rows"} and
                         type(item["missing_rows"]) is int and item["missing_rows"] >= 0,
                         "PRODUCER_REPORT_NATIVE_METADATA_NESTED")
            elif type(item) is str:
                allowed = {"schema": {"aql.research.warehouse-source.v1"},
                    "source_class": {"RETROSPECTIVE_NON_PIT"}, "trading_authority": {"NONE"},
                    "status": {"ARCHIVE_IMPORTED"}, "publisher_integrity": {"ZIP_CHECKSUM_MATCH"},
                    "independent_origin_attestation": {"NOT_ATTESTED"}, "timestamp_unit": {"ms", "us"},
                    "registry_action": {"REPAIR_RECOVERY"}, "policy_ref": {"SEALED_SOURCE_REPLAY"}}
                _require(item in allowed.get(key, set()), "PRODUCER_REPORT_NATIVE_METADATA_ENUM")
            else:
                _require((type(item) is int and item >= 0) or
                         (key == "historical_known_at_ms" and item is None),
                         "PRODUCER_REPORT_NATIVE_METADATA_VALUE")


def publish_bounded(report_root, *, protected_root, lane, identity, sequence,
                    observed_ms, published_ms, status, reason, counters,
                    source_sha256=None, receipt_sha256=None,
                    registry_sha256=None, registry_watermark=None,
                    source_day_ms=None, task_state=None,
                    code_sha256=None, config_sha256=None, continuation_sha256=None,
                    continuation_ref=None, accepted_prefix_unchanged=False,
                    checksum_sha256=None, source_receipt_sha256=None,
                    source_key=None, source_receipt=None, import_receipt=None,
                    import_receipt_sha256=None, reuse_committed_daily=False):
    """Atomic create-only fixed-schema report; no warehouse reads or cleanup.

    A deterministic (lane, identity, sequence) path makes replay idempotent;
    different bytes for that slot fail closed. Every publication is opted into
    explicitly by a caller operating on an isolated candidate, not live host.
    """
    _require(type(reuse_committed_daily) is bool and (not reuse_committed_daily or lane == "DAILY"),
             "PRODUCER_REPORT_REUSE_SCOPE")
    _require(lane in ("HISTORY", "DAILY"), "PRODUCER_REPORT_LANE")
    _require(type(identity) is str and TOKEN.fullmatch(identity), "PRODUCER_REPORT_ID")
    _require(type(sequence) is int and 0 <= sequence <= 10**15,
             "PRODUCER_REPORT_SEQUENCE")
    _require(type(observed_ms) is int and observed_ms > 0 and
             type(published_ms) is int and published_ms >= observed_ms,
             "PRODUCER_REPORT_CLOCK")
    _require(type(status) is str and TOKEN.fullmatch(status) and
             type(reason) is str and TOKEN.fullmatch(reason),
             "PRODUCER_REPORT_STATUS")
    _require(type(counters) is dict and len(counters) <= 12 and all(
        type(k) is str and TOKEN.fullmatch(k) and
        type(v) is int and 0 <= v <= 10**15 for k, v in counters.items()
    ), "PRODUCER_REPORT_COUNTERS")
    _require(all(_hex_or_none(v) for v in
        (source_sha256, receipt_sha256, registry_sha256,
         code_sha256, config_sha256, continuation_sha256,
         checksum_sha256, source_receipt_sha256, import_receipt_sha256)),
        "PRODUCER_REPORT_DIGEST")
    _require(registry_watermark is None or
             (type(registry_watermark) is int and registry_watermark >= 0),
             "PRODUCER_REPORT_WATERMARK")
    _require(continuation_ref is None or (type(continuation_ref) is str and
             continuation_ref.startswith('https://github.com/scannercrypto0-gif/super-kumo-v8/')
             and len(continuation_ref) <= 250), 'PRODUCER_REPORT_CONTINUATION')
    _require(type(accepted_prefix_unchanged) is bool,
             'PRODUCER_REPORT_PREFIX')
    _require(source_day_ms is None or
             (type(source_day_ms) is int and source_day_ms > 0
              and source_day_ms % 86400000 == 0),
             "PRODUCER_REPORT_SOURCE_DAY")
    _require(task_state is None or
             (type(task_state) is str and TOKEN.fullmatch(task_state)),
             "PRODUCER_REPORT_TASK_STATE")

    _require(source_key is None or (type(source_key) is str and len(source_key) <= 160
             and source_key.startswith("data/spot/daily/klines/BTCUSDT/1m/")),
             "PRODUCER_REPORT_SOURCE_KEY")
    _require(source_receipt is None or type(source_receipt) is dict, "PRODUCER_REPORT_SOURCE_RECEIPT")
    _require(import_receipt is None or type(import_receipt) is dict, "PRODUCER_REPORT_IMPORT_RECEIPT")
    _daily_metadata(source_receipt, import_receipt)
    root = _safe_path(report_root)
    protected = _safe_path(protected_root)
    _require(root != protected and not root.is_relative_to(protected)
             and not protected.is_relative_to(root),
             "PRODUCER_REPORT_ROOT_OVERLAP")
    _require(root.is_dir(), "PRODUCER_REPORT_ROOT_MUST_PREEXIST")
    _require(root.stat().st_nlink >= 1, "PRODUCER_REPORT_ROOT_INVALID")
    body = dict(schema=("aql.warehouse.full-history-checkpoint.v1"
                        if lane == "HISTORY" else "aql.mcp.producer-bounded-report.v1"),
                lane=lane, producer_identity=identity, sequence=sequence,
                observation_ms=observed_ms, published_ms=published_ms,
                status=status, reason=reason, counters=counters,
                source_sha256=source_sha256, receipt_sha256=receipt_sha256,
                checksum_sha256=checksum_sha256,
                source_receipt_sha256=source_receipt_sha256,
                source_key=source_key, source_receipt=source_receipt,
                import_receipt=import_receipt, import_receipt_sha256=import_receipt_sha256,
                registry_sha256=registry_sha256,
                registry_watermark=registry_watermark,
                code_sha256=code_sha256, config_sha256=config_sha256,
                continuation_sha256=continuation_sha256,
                source_day_ms=source_day_ms, task_state=task_state,
                source_class="RETROSPECTIVE_NON_PIT",
                full_history_verified=False if lane == "HISTORY" else None,
                publisher_import_registry_verified=bool(
                    lane == "DAILY" and source_sha256 and receipt_sha256 and
                    registry_sha256 and registry_watermark is not None and
                    checksum_sha256 and source_receipt_sha256),
                trading_authority="NONE",
                evidence_grade="PRODUCER_REPORTED_NOT_INDEPENDENTLY_REVALIDATED")
    if lane == "HISTORY":
        body.update(continuation_ref=continuation_ref or "",
                    accepted_prefix_unchanged=accepted_prefix_unchanged,
                    archives_this_run=counters.get("archives_this_run", 0),
                    inserted_rows_this_run=counters.get("inserted_rows_this_run", 0),
                    observed_at_ms=observed_ms)
    body["report_sha256"] = hashlib.sha256(json.dumps(body, sort_keys=True, separators=(",", ":"),
        allow_nan=False).encode("utf-8")).hexdigest()
    raw = json.dumps(body, sort_keys=True, separators=(",", ":"),
                     allow_nan=False).encode("utf-8")
    _require(len(raw) <= MAX_REPORT_BYTES, "PRODUCER_REPORT_SIZE")
    digest = hashlib.sha256(raw).hexdigest()
    destination = _safe_path(root / f"{lane.lower()}-{identity}-{sequence:015d}.json")
    _require(destination.parent == root, "PRODUCER_REPORT_ROOT_ESCAPE")
    if destination.exists():
        if reuse_committed_daily:
            _require(destination.is_file() and destination.stat().st_nlink == 1
                     and 0 < destination.stat().st_size <= MAX_REPORT_BYTES,
                     "PRODUCER_REPORT_REPLAY_CONFLICT")
            original_raw = destination.read_bytes()
            original = json.loads(original_raw)
            original_body = {k: v for k, v in original.items() if k != "report_sha256"}
            original_seal = hashlib.sha256(json.dumps(original_body, sort_keys=True,
                separators=(",", ":"), allow_nan=False).encode("utf-8")).hexdigest()
            stable = ("schema", "lane", "producer_identity", "sequence", "source_sha256",
                      "checksum_sha256", "source_receipt_sha256", "source_key", "source_day_ms",
                      "code_sha256", "config_sha256", "source_class", "trading_authority")
            _require(original.get("report_sha256") == original_seal
                     and all(original.get(k) == body.get(k) for k in stable)
                     and type(original.get("observation_ms")) is int
                     and type(original.get("published_ms")) is int
                     and original["observation_ms"] <= observed_ms
                     and original["published_ms"] <= published_ms,
                     "PRODUCER_REPORT_REPLAY_CONFLICT")
            # The first committed evidence remains authoritative and may now be
            # stale. Never retimestamp it or imply another automatic host cycle.
            return dict(name=destination.name, sha256=hashlib.sha256(original_raw).hexdigest(),
                        replay=True, original_observation_preserved=True)
        _require(destination.is_file() and destination.stat().st_nlink == 1
                 and destination.read_bytes() == raw,
                 "PRODUCER_REPORT_REPLAY_CONFLICT")
        return dict(name=destination.name, sha256=digest, replay=True)
    fd, temp_name = tempfile.mkstemp(prefix=".pending-", dir=root)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        # link is atomic and refuses to replace an existing report; both
        # names live on the same volume. Never delete an existing report.
        try:
            os.link(temp_name, destination)
        except FileExistsError:
            _require(destination.is_file() and destination.stat().st_nlink == 1
                     and destination.read_bytes() == raw,
                     "PRODUCER_REPORT_REPLAY_CONFLICT")
        return dict(name=destination.name, sha256=digest,
                    replay=False)
    finally:
        Path(temp_name).unlink(missing_ok=True)
