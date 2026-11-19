"""Offline 1m capture spool: atomic pinned JSONL handoff for research import.

The caller supplies frames; this module never opens a socket, schedules a task,
or represents synthetic/offline input as authenticated Binance data.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from tempfile import NamedTemporaryFile

from aql.research_ws_1m_ingest import project_closed_1m_frame


def seal_capture(root, frames, received_at_ms, *, max_frames=1440):
    root = Path(root)
    if root.is_symlink():
        raise ValueError("CAPTURE_ROOT_SYMLINK")
    if not isinstance(frames, list) or not 1 <= len(frames) <= max_frames <= 1440:
        raise ValueError("CAPTURE_BOUND")
    rows = [project_closed_1m_frame(raw, received_at_ms=received_at_ms)
            for raw in frames]
    if any(rows[i]["open_ms"] != rows[i-1]["open_ms"] + 60000
           for i in range(1, len(rows))):
        raise ValueError("CAPTURE_GAP_DUPLICATE")
    raw = b"".join(frame + b"\n" for frame in frames)
    pin = hashlib.sha256(raw).hexdigest()
    root.mkdir(parents=True, exist_ok=True)
    target = root / (pin + ".jsonl")
    if target.exists():
        if target.is_symlink() or hashlib.sha256(target.read_bytes()).hexdigest() != pin:
            raise ValueError("CAPTURE_REWRITE_DENIED")
    else:
        with NamedTemporaryFile(dir=root, delete=False) as stream:
            scratch = Path(stream.name)
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        try:
            try:
                os.link(scratch, target)
            except FileExistsError:
                if target.is_symlink() or hashlib.sha256(target.read_bytes()).hexdigest() != pin:
                    raise ValueError("CAPTURE_REWRITE_DENIED")
        finally:
            scratch.unlink()
    return {"status": "OFFLINE_CAPTURE_SEALED",
            "path": str(target), "sha256": pin, "frames": len(rows),
            "first_open_ms": rows[0]["open_ms"],
            "last_open_ms": rows[-1]["open_ms"],
            "received_at_ms": received_at_ms,
            "source_authenticity": "NOT_INDEPENDENTLY_ATTESTED",
            "trading_authority": "NONE"}
