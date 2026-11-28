"""Read-only boundary between forward research 15m store and historical Scanner E.

Never forges Core #253 warehouse/query receipts or Scanner selection.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
from aql.research_bar_store import ResearchBarStore
from aql.research_durability_readback import verify_research_window


def inspect_forward_15m(store_path, open_ms):
    if type(open_ms) is not int or open_ms < 0 or open_ms % 900000:
        raise ValueError("15M_GRID_REQUIRED")
    with ResearchBarStore(store_path) as store:
        proof = verify_research_window(store, symbol="BTCUSDT", interval="15m", open_ms=open_ms)
        bar = store.read("BTCUSDT", "15m", open_ms)
    if proof["source_class"] != "FORWARD_UNQUALIFIED" or bar["sha256"] != proof["projection_sha256"]:
        raise ValueError("FORWARD_15M_SOURCE_CLASS_OR_DIGEST")
    return {
        "schema": "aql.research.forward-15m-scanner-boundary.v1",
        "status": "FORWARD_15M_DURABLE_READABLE",
        "symbol": "BTCUSDT", "interval": "15m", "open_ms": open_ms,
        "bar_sha256": bar["sha256"], "constituent_count": proof["constituent_count"],
        "available_at_ms": proof["available_at_ms"],
        "source_class": "FORWARD_UNQUALIFIED",
        "core_e_warehouse_receipt": None, "core_253_local_query_receipt": None,
        "scanner_e_historical_route": "WAIT_CORE_HISTORICAL_CONTRACT_NOT_SATISFIED",
        "scanner_attempts": 0, "factory_experiments": 0,
        "secretary": "WAIT", "orders": 0, "trading_authority": "NONE",
        "scientific_pit_oos": "NOT_ATTESTED",
        "publisher_authenticity": "NOT_INDEPENDENTLY_ATTESTED",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--store", type=Path, required=True)
    parser.add_argument("--open-ms", type=int, required=True)
    args = parser.parse_args()
    print(json.dumps(inspect_forward_15m(args.store, args.open_ms), sort_keys=True))


if __name__ == "__main__":
    main()
