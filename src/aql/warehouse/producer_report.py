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


def publish_bounded(report_root, *, protected_root, lane, identity, sequence,
                    observed_ms, published_ms, status, reason, counters,
                    source_sha256=None, receipt_sha256=None,
                    registry_sha256=None, registry_watermark=None,
                    source_day_ms=None, task_state=None):
    """Atomic create-only fixed-schema report; no warehouse reads or cleanup.

    A deterministic (lane, identity, sequence) path makes replay idempotent;
    different bytes for that slot fail closed. Every publication is opted into
    explicitly by a caller operating on an isolated candidate, not live host.
    """
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
        (source_sha256, receipt_sha256, registry_sha256)),
        "PRODUCER_REPORT_DIGEST")
    _require(registry_watermark is None or
             (type(registry_watermark) is int and registry_watermark >= 0),
             "PRODUCER_REPORT_WATERMARK")
    _require(source_day_ms is None or
             (type(source_day_ms) is int and source_day_ms > 0
              and source_day_ms % 86400000 == 0),
             "PRODUCER_REPORT_SOURCE_DAY")
    _require(task_state is None or
             (type(task_state) is str and TOKEN.fullmatch(task_state)),
             "PRODUCER_REPORT_TASK_STATE")

    root = _safe_path(report_root)
    protected = _safe_path(protected_root)
    _require(root != protected and not root.is_relative_to(protected)
             and not protected.is_relative_to(root),
             "PRODUCER_REPORT_ROOT_OVERLAP")
    _require(root.is_dir(), "PRODUCER_REPORT_ROOT_MUST_PREEXIST")
    _require(root.stat().st_nlink >= 1, "PRODUCER_REPORT_ROOT_INVALID")
    body = dict(schema="aql.mcp.producer-bounded-report.v1",
                lane=lane, producer_identity=identity, sequence=sequence,
                observation_ms=observed_ms, published_ms=published_ms,
                status=status, reason=reason, counters=counters,
                source_sha256=source_sha256, receipt_sha256=receipt_sha256,
                registry_sha256=registry_sha256,
                registry_watermark=registry_watermark,
                source_day_ms=source_day_ms, task_state=task_state,
                source_class="RETROSPECTIVE_NON_PIT",
                full_history_verified=False if lane == "HISTORY" else None,
                publisher_import_registry_verified=bool(
                    lane == "DAILY" and source_sha256 and receipt_sha256 and
                    registry_sha256 and registry_watermark is not None),
                trading_authority="NONE")
    raw = json.dumps(body, sort_keys=True, separators=(",", ":"),
                     allow_nan=False).encode("utf-8")
    _require(len(raw) <= MAX_REPORT_BYTES, "PRODUCER_REPORT_SIZE")
    digest = hashlib.sha256(raw).hexdigest()
    destination = _safe_path(root / f"{lane.lower()}-{identity}-{sequence:015d}.json")
    _require(destination.parent == root, "PRODUCER_REPORT_ROOT_ESCAPE")
    if destination.exists():
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
            _require(destination.read_bytes() == raw,
                     "PRODUCER_REPORT_REPLAY_CONFLICT")
        return dict(name=destination.name, sha256=digest,
                    replay=False)
    finally:
        Path(temp_name).unlink(missing_ok=True)
