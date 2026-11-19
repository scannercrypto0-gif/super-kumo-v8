"""Explicit owner-invoked, bounded Binance 1m research capture.

Never runs on import, in CI, or as a scheduled task. No trading.
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from aql.research_1m_collector import collect_authorized_1m

ENDPOINT = "wss://data-stream.binance.vision/ws/btcusdt@kline_1m"
AUTHORIZATION = "OWNER_AUTHORIZED_ORIGINAL_1M_RESEARCH_CAPTURE"


def capture_live(*, spool_dir, authorization, frame_limit=5, wall_seconds=420,
                 connection_factory=None, monotonic=None, clock_ms=None):
    if authorization != AUTHORIZATION:
        raise ValueError("ORIGINAL_CAPTURE_AUTHORIZATION_REQUIRED")
    if (type(frame_limit) is not int or not 1 <= frame_limit <= 30
            or type(wall_seconds) is not int or not 60 <= wall_seconds <= 1800):
        raise ValueError("LIVE_CAPTURE_BUDGET_INVALID")
    if monotonic is None:
        monotonic = time.monotonic
    if clock_ms is None:
        clock_ms = lambda: time.time_ns() // 1000000
    if connection_factory is None:
        import websocket
        connection_factory = websocket.create_connection
    started = monotonic()
    # A hard deadline is checked before each blocking receive.
    connection = connection_factory(ENDPOINT, timeout=5, enable_multithread=True)
    try:
        def reader():
            from websocket import ABNF
            remaining = wall_seconds - (monotonic() - started)
            if remaining <= 0:
                raise ValueError("LIVE_CAPTURE_DEADLINE")
            connection.settimeout(min(5, remaining))
            opcode, raw = connection.recv_data(control_frame=True)
            if opcode == ABNF.OPCODE_PING:
                connection.pong(raw)
                return ("ping", raw)
            if opcode == ABNF.OPCODE_PONG:
                return ("pong", raw)
            if opcode != ABNF.OPCODE_TEXT:
                raise ValueError("LIVE_CAPTURE_UNEXPECTED_OPCODE")
            return ("text", raw if type(raw) is bytes else raw.encode("utf-8"))

        return collect_authorized_1m(
            reader=reader, clock_ms=clock_ms, spool_dir=spool_dir,
            authorization=authorization, frame_limit=frame_limit,
            event_limit=frame_limit * 300)
    finally:
        connection.close()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spool-dir", required=True, type=Path)
    parser.add_argument("--frame-limit", type=int, default=5)
    parser.add_argument("--wall-seconds", type=int, default=420)
    parser.add_argument("--authorize-original-1m-research-capture",
                        action="store_true", required=True)
    args = parser.parse_args(argv)
    receipt = capture_live(
        spool_dir=args.spool_dir,
        authorization=AUTHORIZATION if args.authorize_original_1m_research_capture else "",
        frame_limit=args.frame_limit, wall_seconds=args.wall_seconds)
    print(json.dumps(receipt, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
