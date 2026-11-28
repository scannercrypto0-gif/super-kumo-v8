"""Read-only bounded durability proof for research-only finalized 1m bars.

Does not certify original publisher identity, Core/Scanner/Factory integration,
PIT/OOS eligibility, or trading authority.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from aql.research_bar_store import ResearchBarStore
from aql.research_timeframes import MINUTE, WIDTHS


def verify_research_window(store, *, symbol, interval, open_ms):
    if interval not in WIDTHS:
        raise ValueError("INTERVAL_UNSUPPORTED")
    if type(open_ms) is not int or open_ms < 0:
        raise ValueError("WINDOW_REQUIRED")
    count = WIDTHS[interval]
    source_classes = set()
    digest = hashlib.sha256()
    for i in range(count):
        row = store.read(symbol, "1m", open_ms + i * MINUTE)
        if row is None:
            raise ValueError("SOURCE_GAP")
        source_classes.add(row["source_class"])
        digest.update(bytes.fromhex(row["sha256"]))
    if len(source_classes) != 1:
        raise ValueError("MIXED_SOURCE_CLASS")
    # Projection is deterministic but persists its immutable digest; read back
    # through a second connection to verify actual SQLite durability.
    projected = store.project(symbol, interval, open_ms)
    with ResearchBarStore(store.path) as second:
        durable = second.read(symbol, interval, open_ms)
        if durable != projected:
            raise ValueError("DURABILITY_READBACK_FAILED")
    return {
        "status": "RESEARCH_DURABILITY_READBACK_PASS",
        "symbol": symbol, "interval": interval, "open_ms": open_ms,
        "constituent_count": count, "source_class": source_classes.pop(),
        "constituent_digest_chain_sha256": digest.hexdigest(),
        "projection_sha256": projected["sha256"],
        "available_at_ms": projected["available_at_ms"],
        "source_authenticity": "NOT_INDEPENDENTLY_ATTESTED",
        "core_scanner_factory_secretary_e2e": "NOT_ATTESTED",
        "scientific_pit_oos": "NOT_ATTESTED",
        "trading_authority": "NONE",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--store", type=Path, required=True)
    parser.add_argument("--symbol", default="BTCUSDT")
    parser.add_argument("--interval", choices=sorted(WIDTHS), required=True)
    parser.add_argument("--open-ms", type=int, required=True)
    args = parser.parse_args()
    with ResearchBarStore(args.store) as store:
        result = verify_research_window(store, symbol=args.symbol,
                                        interval=args.interval, open_ms=args.open_ms)
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
