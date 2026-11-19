"""One-shot, offline, pinned original-frame bridge into the research-only store.

Input is a locally captured JSONL file of Binance websocket frames, not health logs.
Never opens sockets, modifies scheduled tasks, or publishes original market bytes.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from aql.research_bar_store import ResearchBarStore
from aql.research_ws_1m_ingest import project_closed_1m_frame


def import_pinned_ws_jsonl(store, path, *, expected_sha256, received_at_ms, max_frames=10080):
    source = Path(path)
    if not source.is_file() or source.is_symlink():
        raise ValueError("SOURCE_FILE_REQUIRED")
    if (type(expected_sha256) is not str or len(expected_sha256) != 64
            or any(c not in "0123456789abcdef" for c in expected_sha256)):
        raise ValueError("PIN_REQUIRED")
    if type(received_at_ms) is not int or received_at_ms < 0:
        raise ValueError("RECEIPT_CLOCK_REQUIRED")
    if type(max_frames) is not int or not 1 <= max_frames <= 10080:
        raise ValueError("FRAME_BOUND")
    if source.stat().st_size > max_frames * 65537:
        raise ValueError("SOURCE_TOO_LARGE")
    raw = source.read_bytes()
    if len(raw) > max_frames * 65537:
        raise ValueError("SOURCE_TOO_LARGE")
    if hashlib.sha256(raw).hexdigest() != expected_sha256:
        raise ValueError("SOURCE_PIN_MISMATCH")
    frames = raw.splitlines()
    if not 1 <= len(frames) <= max_frames:
        raise ValueError("FRAME_COUNT_INVALID")
    # One transaction for the entire source: fail closed without partial writes.
    rows = [project_closed_1m_frame(frame, received_at_ms=received_at_ms)
            for frame in frames]
    if any(rows[i]["open_ms"] != rows[i - 1]["open_ms"] + 60000
           for i in range(1, len(rows))):
        raise ValueError("SOURCE_GAP_DUPLICATE")
    store.insert_batch(rows)
    return {"status": "PINNED_WS_SOURCE_IMPORTED", "frame_count": len(rows),
            "source_file_sha256": expected_sha256, "first_open_ms": rows[0]["open_ms"],
            "last_open_ms": rows[-1]["open_ms"],
            "source_authenticity": "NOT_INDEPENDENTLY_ATTESTED",
            "trading_authority": "NONE", "scientific_promotion": "BLOCKED"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--sha256", required=True)
    parser.add_argument("--received-at-ms", type=int, required=True)
    parser.add_argument("--store", type=Path, required=True)
    args = parser.parse_args()
    with ResearchBarStore(args.store) as store:
        result = import_pinned_ws_jsonl(store, args.source, expected_sha256=args.sha256,
                                         received_at_ms=args.received_at_ms)
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
