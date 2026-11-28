"""Owner-invoked bounded original 1m capture -> pinned durable research readback.

No scheduler mutation, no existing 15m service changes, no trading.
The operational receipt is NOT an independent publisher/PIT attestation.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from aql.research_live_1m_capture import AUTHORIZATION, capture_live
from aql.research_offline_one_shot import run_one_shot


def run_live_research_one_shot(*, spool_dir, store_path, authorization,
                               frame_limit=5, wall_seconds=900,
                               interval="5m", capture=capture_live):
    if authorization != AUTHORIZATION:
        raise ValueError("ORIGINAL_CAPTURE_AUTHORIZATION_REQUIRED")
    if interval not in ("5m", "15m"):
        raise ValueError("LIVE_RESEARCH_INTERVAL_UNSUPPORTED")
    width = {"5m": 5, "15m": 15}[interval]
    if frame_limit < width:
        raise ValueError("CAPTURE_TOO_SHORT_FOR_INTERVAL")
    sealed = capture(spool_dir=spool_dir, authorization=authorization,
                     frame_limit=frame_limit, wall_seconds=wall_seconds,
                     alignment_minutes=width)
    if (sealed.get("status") != "OFFLINE_CAPTURE_SEALED"
            or sealed.get("source_authenticity") != "NOT_INDEPENDENTLY_ATTESTED"
            or sealed.get("frames") != frame_limit):
        raise ValueError("CAPTURE_RECEIPT_INVALID")
    # The importer independently re-hashes the captured file before staging.
    result = run_one_shot(store_path=store_path, source_path=Path(sealed["path"]),
                          sha256=sealed["sha256"], source_kind="ws_jsonl",
                          source_clock_ms=sealed["received_at_ms"], interval=interval)
    return {"status": "CAPTURE_TO_DURABLE_RESEARCH_PASS",
            "capture": sealed, "durability": result,
            "binance_source_authenticity": "NOT_INDEPENDENTLY_ATTESTED",
            "core_scanner_factory_e2e": "NOT_ATTESTED",
            "scientific_promotion": "BLOCKED",
            "trading_authority": "NONE"}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spool-dir", type=Path, required=True)
    parser.add_argument("--store", type=Path, required=True)
    parser.add_argument("--frame-limit", type=int, default=5)
    parser.add_argument("--wall-seconds", type=int, default=900)
    parser.add_argument("--interval", choices=("5m", "15m"), default="5m")
    parser.add_argument("--authorize-original-1m-research-capture",
                        action="store_true", required=True)
    args = parser.parse_args(argv)
    print(json.dumps(run_live_research_one_shot(
        spool_dir=args.spool_dir, store_path=args.store,
        authorization=AUTHORIZATION if args.authorize_original_1m_research_capture else "",
        frame_limit=args.frame_limit, wall_seconds=args.wall_seconds,
        interval=args.interval), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
