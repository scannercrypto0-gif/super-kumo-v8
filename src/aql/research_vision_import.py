"""Offline, explicitly pinned Binance Vision 1m CSV importer.

No network, no task activation, no claim of publisher authentication.
The caller must independently verify source rights and archive custody.
"""
from __future__ import annotations

import csv
import hashlib
from pathlib import Path

from aql.research_bar_store import ResearchBarStore
from aql.research_timeframes import MINUTE


def import_pinned_vision_csv(store: ResearchBarStore, path, *, symbol, expected_sha256,
                             available_at_ms, max_rows=1500):
    source = Path(path)
    if not source.is_file() or source.is_symlink():
        raise ValueError("SOURCE_FILE_REQUIRED")
    if not isinstance(expected_sha256, str) or len(expected_sha256) != 64 or any(
            c not in "0123456789abcdef" for c in expected_sha256):
        raise ValueError("PIN_REQUIRED")
    if type(available_at_ms) is not int or available_at_ms < 0:
        raise ValueError("AVAILABILITY_REQUIRED")
    if type(max_rows) is not int or not 1 <= max_rows <= 10080:
        raise ValueError("BOUND_REQUIRED")
    # Read and verify complete source before any repository mutation.
    raw = source.read_bytes()
    if len(raw) > max_rows * 512:
        raise ValueError("SOURCE_TOO_LARGE")
    if hashlib.sha256(raw).hexdigest() != expected_sha256:
        raise ValueError("SOURCE_PIN_MISMATCH")
    try:
        lines = raw.decode("utf-8-sig").splitlines()
        parsed = list(csv.reader(lines, strict=True))
    except (UnicodeError, csv.Error) as exc:
        raise ValueError("SOURCE_CSV_INVALID") from exc
    if not 1 <= len(parsed) <= max_rows:
        raise ValueError("ROW_COUNT_INVALID")
    rows = []
    previous = None
    for record in parsed:
        if len(record) != 12:
            raise ValueError("VISION_NATIVE_SCHEMA")
        try:
            opened, closed = int(record[0]), int(record[6])
        except ValueError as exc:
            raise ValueError("VISION_TIME_INVALID") from exc
        if opened < 0 or opened % MINUTE or closed != opened + MINUTE - 1:
            raise ValueError("VISION_1M_GRID")
        if previous is not None and opened != previous + MINUTE:
            raise ValueError("VISION_GAP_DUPLICATE")
        previous = opened
        if available_at_ms < opened + MINUTE:
            raise ValueError("SOURCE_AVAILABILITY_INVALID")
        row_sha = hashlib.sha256(",".join(record).encode("utf-8")).hexdigest()
        rows.append(dict(symbol=symbol, interval="1m", open_ms=opened, final=True,
                         o=record[1], h=record[2], l=record[3], c=record[4],
                         v=record[5], source_sha256=row_sha,
                         available_at_ms=available_at_ms))
    # Validate entire batch before any write, then preserve immutable rows.
    from aql.research_timeframes import project_finalized_1m
    for row in rows:
        project_finalized_1m([row], "1m", source_class="RETROSPECTIVE_NON_PIT")
    projected = [project_finalized_1m([row], "1m", source_class="RETROSPECTIVE_NON_PIT")
                 for row in rows]
    store.insert_batch(projected)
    return {"status": "RETROSPECTIVE_NON_PIT_IMPORTED",
            "rows": len(rows), "source_sha256": expected_sha256,
            "first_open_ms": rows[0]["open_ms"], "last_open_ms": rows[-1]["open_ms"],
            "source_authenticity": "NOT_INDEPENDENTLY_ATTESTED",
            "trading_authority": "NONE"}
