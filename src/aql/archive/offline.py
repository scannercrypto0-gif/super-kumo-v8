"""Read-only bounded query contract for finalized, verified backup generations.

No research runtime import, dataset registration or PIT eligibility conversion.
Caller must supply a previously retained inventory digest and a quiescent copy.
"""
from contextlib import closing
import sqlite3
import time

from .backup import verify_backup
from .contracts import canonical, digest, timestamp
from .local import check_path, child, verify_segment


def snapshot(root, *, expected_digest, symbol, interval, start_ms, end_ms,
             max_rows=4096, max_bytes=2_000_000_000, timeout=60):
    """Return canonical bytes or raise; never return a truncated success.

    Full backup verification precedes selection, so a query cannot hide a corrupt
    unselected record. Selection is [start,end) on bar open, not availability.
    Output is retrospective evidence only, never a HistoricalLibrary manifest.
    """
    timestamp(start_ms); timestamp(end_ms)
    if start_ms >= end_ms:
        raise ValueError("Nonempty open-time range required")
    if any(type(v) is not str or not 1 <= len(v) <= 64 for v in (symbol, interval)):
        raise ValueError("Explicit bounded symbol/interval required")
    if type(max_rows) is not int or not 1 <= max_rows <= 4096:
        raise ValueError("Query row limit must be1..4096")
    root = check_path(root)
    deadline = time.monotonic()+timeout
    evidence = verify_backup(root, expected_digest=expected_digest,
                             max_bytes=max_bytes, timeout=max(0, deadline-time.monotonic()))
    selected = []
    # immutable is safe only for this sealed backup output, never a live catalog.
    uri = (root/"archive/catalog.sqlite").as_uri()+"?mode=ro&immutable=1"
    with closing(sqlite3.connect(uri, uri=True)) as catalog:
        catalog.set_progress_handler(lambda: int(time.monotonic() > deadline), 1000)
        for relative, mh in catalog.execute("SELECT path,manifest_hash FROM segments ORDER BY path"):
            if time.monotonic() > deadline:
                raise TimeoutError("Offline query deadline")
            rows, _ = verify_segment(child(root/"archive", relative), expected_hash=mh)
            for row in rows:
                bar = row["bar"]
                if (bar["symbol"] == symbol and bar["interval"] == interval
                        and start_ms <= bar["bar_open"] < end_ms):
                    if len(selected) >= max_rows:
                        raise ValueError("Query row limit exceeded; no truncated result")
                    selected.append(row)
    selected.sort(key=lambda row: (row["bar"]["bar_open"], row["record_id"], row["source_seq"]))
    # Reverify after selection: changed bytes cannot escape through an early yield.
    if verify_backup(root, expected_digest=expected_digest, max_bytes=max_bytes, timeout=max(0, deadline-time.monotonic())) != evidence:
        raise ValueError("Backup changed during query")
    result = {"schema": "aql.offline-archive-query.v1", "inventory_hash": expected_digest,
              "selection": {"symbol": symbol, "interval": interval,
                            "start_open_ms": start_ms, "end_open_ms_exclusive": end_ms},
              "records": selected, "count": len(selected),
              "record_content_hash": digest(selected),
              "watermark": evidence["watermark"],
              "unarchived_records": evidence["journal_records"]-evidence["records"],
              "coverage": "ARCHIVED_RECORDS_ONLY_NOT_FULL_MARKET",
              "retrospective_only": True, "pit_eligibility": "NOT_ATTESTED",
              "independent_custody_verified": False,
              "research_evaluation": "NOT_PERFORMED"}
    return canonical(result)
