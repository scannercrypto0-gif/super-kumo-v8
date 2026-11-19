"""Offline one-shot research data custody and durability proof.

Only imports already captured/pinned 1m source files. Never starts Binance
connections, scheduler tasks, research decisions, or trading.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from aql.research_bar_store import ResearchBarStore
from aql.research_durability_readback import verify_research_window
from aql.research_vision_import import import_pinned_vision_csv
from aql.research_ws_capture_import import import_pinned_ws_jsonl


def run_one_shot(*, store_path, source_path, sha256, source_kind,
                 source_clock_ms, interval="5m", symbol="BTCUSDT"):
    with ResearchBarStore(store_path) as store:
        if source_kind == "vision_csv":
            imported = import_pinned_vision_csv(
                store, source_path, symbol=symbol, expected_sha256=sha256,
                available_at_ms=source_clock_ms)
        elif source_kind == "ws_jsonl":
            if symbol != "BTCUSDT":
                raise ValueError("WS_SYMBOL_UNSUPPORTED")
            imported = import_pinned_ws_jsonl(
                store, source_path, expected_sha256=sha256,
                received_at_ms=source_clock_ms)
        else:
            raise ValueError("SOURCE_KIND_UNSUPPORTED")
        first = imported["first_open_ms"]
        from aql.research_timeframes import WIDTHS, MINUTE
        width = WIDTHS[interval] * MINUTE
        # The proof window must be fully covered by this exact pinned source.
        if interval == "1w":
            # UTC weeks start Monday, not Unix epoch Thursday.
            from datetime import datetime, timezone
            dt = datetime.fromtimestamp(first / 1000, tz=timezone.utc)
            weekday_offset = (dt.weekday() * 86400000
                              + dt.hour * 3600000 + dt.minute * 60000
                              + dt.second * 1000 + dt.microsecond // 1000)
            start = first - weekday_offset
            if start < first:
                start += width
        else:
            start = ((first + width - 1) // width) * width
        if start + width - MINUTE > imported["last_open_ms"]:
            raise ValueError("SOURCE_WINDOW_INCOMPLETE")
        durable = verify_research_window(store, symbol=symbol,
                                         interval=interval, open_ms=start)
        return {
            "status": "OFFLINE_PINNED_SOURCE_DURABILITY_PASS",
            "source": imported, "durability": durable,
            "operational_core_scanner_factory_secretary": "NOT_ATTESTED",
            "publisher_authenticity": "NOT_INDEPENDENTLY_ATTESTED",
            "scientific_promotion": "BLOCKED", "trading_authority": "NONE",
        }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--store", type=Path, required=True)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--sha256", required=True)
    parser.add_argument("--source-kind", choices=("vision_csv", "ws_jsonl"), required=True)
    parser.add_argument("--source-clock-ms", type=int, required=True)
    parser.add_argument("--interval", choices=("5m", "15m", "30m", "1h", "1d", "1w"), default="5m")
    parser.add_argument("--symbol", default="BTCUSDT")
    args = parser.parse_args()
    print(json.dumps(run_one_shot(
        store_path=args.store, source_path=args.source, sha256=args.sha256,
        source_kind=args.source_kind, source_clock_ms=args.source_clock_ms,
        interval=args.interval, symbol=args.symbol), sort_keys=True))


if __name__ == "__main__":
    main()
