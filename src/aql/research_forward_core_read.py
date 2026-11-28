"""Forward-only Core research read seam over immutable finalized 15m bars.

Does not impersonate historical Core #253, invoke Scanner E or authorize orders.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
from aql.research_bar_store import ResearchBarStore
from aql.research_durability_readback import verify_research_window

STEP = 900000


def forward_core_window(store_path, *, start_ms, bar_count=12):
    if (type(start_ms) is not int or start_ms < 0 or start_ms % STEP
            or type(bar_count) is not int or not 1 <= bar_count <= 96):
        raise ValueError("FORWARD_CORE_WINDOW_SCOPE")
    rows = []
    with ResearchBarStore(store_path) as store:
        for i in range(bar_count):
            open_ms = start_ms + i * STEP
            # Only consume existing finalized projections. No synthetic fills.
            row = store.read("BTCUSDT", "15m", open_ms)
            if row is None:
                break
            proof = verify_research_window(store, symbol="BTCUSDT", interval="15m", open_ms=open_ms)
            if row["sha256"] != proof["projection_sha256"] or row["source_class"] != "FORWARD_UNQUALIFIED":
                raise ValueError("FORWARD_CORE_PARENT_INVALID")
            rows.append({"open_ms": open_ms, "bar_sha256": row["sha256"],
                         "available_at_ms": row["available_at_ms"],
                         "o": row["o"], "h": row["h"], "l": row["l"],
                         "c": row["c"], "v": row["v"]})
    complete = len(rows) == bar_count
    return {
        "schema": "aql.research.forward-core-read.v1",
        "status": "FORWARD_CORE_WINDOW_READY" if complete else "WAIT_MORE_FINALIZED_15M",
        "symbol": "BTCUSDT", "interval": "15m",
        "start_ms": start_ms, "required_bars": bar_count, "available_bars": len(rows),
        "bars": rows, "source_class": "FORWARD_UNQUALIFIED",
        "core_253_historical_query": "NOT_CLAIMED",
        "scanner_e_historical_route": "WAIT",
        "strategy_evaluation": "NOT_EXECUTED",
        "factory_experiments": 0, "secretary": "WAIT",
        "orders": 0, "trading_authority": "NONE",
        "scientific_pit_oos": "NOT_ATTESTED",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--store", type=Path, required=True)
    parser.add_argument("--start-ms", type=int, required=True)
    parser.add_argument("--bar-count", type=int, default=12)
    args = parser.parse_args()
    print(json.dumps(forward_core_window(args.store, start_ms=args.start_ms,
                                          bar_count=args.bar_count), sort_keys=True))


if __name__ == "__main__":
    main()
