"""Read-only compatibility gate between existing 15m service and 1m research store.

This gate deliberately does NOT convert sanitized operational receipts to OHLC.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def inspect_service_bridge(receipts_dir, *, expected_interval="1m", max_files=500):
    root = Path(receipts_dir)
    if not root.is_dir() or root.is_symlink():
        return {"status": "SERVICE_RECEIPTS_UNAVAILABLE",
                "research_source_compatible": False,
                "original_1m_ohlcv": "NOT_ATTESTED",
                "trading_authority": "NONE"}
    files = sorted(root.glob("*.json"))
    if len(files) > max_files:
        raise ValueError("RECEIPT_COUNT_BOUND")
    verified = 0
    for path in files:
        if path.is_symlink() or not path.is_file() or path.stat().st_size > 65536:
            raise ValueError("RECEIPT_FILE_UNSAFE")
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (UnicodeError, ValueError) as exc:
            raise ValueError("RECEIPT_INVALID") from exc
        if type(value) is not dict or value.get("schema") != "atlas.live-research-service.receipt.v1":
            raise ValueError("RECEIPT_SCHEMA_UNEXPECTED")
        if value.get("retention") != "SANITIZED_RECEIPTS_ONLY":
            raise ValueError("RECEIPT_RETENTION_UNEXPECTED")
        verified += 1
    return {
        "status": "EXISTING_SERVICE_NOT_A_1M_OHLC_SOURCE",
        "service_receipts_seen": verified,
        "service_retention": "SANITIZED_RECEIPTS_ONLY",
        "expected_research_interval": expected_interval,
        "research_source_compatible": False,
        "original_1m_ohlcv": "NOT_ATTESTED",
        "integration_next": "SEPARATE_AUTHORIZED_ORIGINAL_1M_CAPTURE_REQUIRED",
        "trading_authority": "NONE",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--receipts-dir", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(inspect_service_bridge(args.receipts_dir), sort_keys=True))


if __name__ == "__main__":
    main()
