"""Bounded research-only 1m collection from an injected, authorized frame reader.

No transport is created here. Existing 15m service remains untouched.
The caller must separately authorize original source acquisition and custody.
"""
from __future__ import annotations

import time

from aql.research_capture_spool import seal_capture
from aql.research_ws_1m_ingest import project_closed_1m_frame


def collect_authorized_1m(*, reader, clock_ms, spool_dir, authorization,
                          frame_limit=5, event_limit=200):
    if authorization != "OWNER_AUTHORIZED_ORIGINAL_1M_RESEARCH_CAPTURE":
        raise ValueError("ORIGINAL_CAPTURE_AUTHORIZATION_REQUIRED")
    if not callable(reader) or not callable(clock_ms):
        raise ValueError("INJECTED_READER_AND_CLOCK_REQUIRED")
    if (type(frame_limit) is not int or not 1 <= frame_limit <= 1440
            or type(event_limit) is not int or not frame_limit <= event_limit <= 10000):
        raise ValueError("CAPTURE_BUDGET_INVALID")
    frames = []
    first = None
    last_received = None
    for _ in range(event_limit):
        kind, raw = reader()
        received = clock_ms()
        if type(received) is not int or received < 0:
            raise ValueError("CAPTURE_CLOCK_INVALID")
        if kind != "text":
            if kind in ("ping", "pong"):
                continue
            raise ValueError("CAPTURE_UNEXPECTED_EVENT")
        # The validator explicitly rejects provisional and foreign candles.
        # Provisional frames are ignored only after strict JSON validation below.
        try:
            row = project_closed_1m_frame(raw, received_at_ms=received)
        except ValueError as exc:
            if str(exc) == "PROVISIONAL_KLINE":
                continue
            raise
        opened = row["open_ms"]
        if first is None:
            first = opened
        elif opened != first + len(frames) * 60000:
            raise ValueError("CAPTURE_GAP_DUPLICATE")
        frames.append(raw)
        last_received = received
        if len(frames) == frame_limit:
            return seal_capture(spool_dir, frames, last_received,
                                max_frames=frame_limit)
    raise ValueError("CAPTURE_BUDGET_EXHAUSTED_NO_OUTPUT")
