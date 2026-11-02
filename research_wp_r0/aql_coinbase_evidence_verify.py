"""Offline evidence integrity verifier for Coinbase public capture.

This is a separate source evidence seam, NOT BinanceCollector/DurableJournal
admission and NOT authenticated PIT provenance.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from research_wp_r0.aql_coinbase_public_candles import normalize_response


class CoinbaseEvidenceError(ValueError):
    pass


def _digest(raw):
    return hashlib.sha256(raw).hexdigest()


def verify_capture(folder):
    folder = Path(folder)
    schedule = json.loads((folder / "schedule.json").read_bytes())
    result = json.loads((folder / "result.json").read_bytes())
    if result.get("status") != "UNVERIFIED_CAPTURED":
        raise CoinbaseEvidenceError("CAPTURE_NOT_SUCCESSFUL")
    if schedule.get("source") != "coinbase_exchange_public_rest" or result.get("source") != schedule["source"]:
        raise CoinbaseEvidenceError("SOURCE_MISMATCH")
    if schedule.get("product_id") != result.get("product_id"):
        raise CoinbaseEvidenceError("PRODUCT_MISMATCH")
    if result.get("execution") != "DISABLED" or result.get("collector_journal_connected") is not False:
        raise CoinbaseEvidenceError("AUTHORITY_SCOPE_MISMATCH")
    raw = (folder / "raw-response.json").read_bytes()
    normalized = (folder / "normalized-bars.json").read_bytes()
    if _digest(raw) != result.get("raw_sha256") or _digest(normalized) != result.get("normalized_sha256"):
        raise CoinbaseEvidenceError("CONTENT_HASH_MISMATCH")
    expected = normalize_response(json.loads(raw), product_id=schedule["product_id"],
                                  received_at_ms=schedule["planned_at_local_ms"])
    observed = json.loads(normalized)
    if len(expected) != result.get("bars") or len(observed) != len(expected):
        raise CoinbaseEvidenceError("BAR_COUNT_MISMATCH")
    for bar, row in zip(expected, observed):
        for field in ("source", "product_id", "interval", "open_time_ms", "close_time_ms",
                      "open", "high", "low", "close", "volume", "custody", "executable_on_binance"):
            if row.get(field) != getattr(bar, field):
                raise CoinbaseEvidenceError("NORMALIZED_CONTENT_MISMATCH")
    return dict(status="LOCAL_UNVERIFIED_EVIDENCE_VERIFIED",
                source=schedule["source"], product_id=schedule["product_id"],
                bars=len(expected), execution="DISABLED",
                journal_connected=False, external_pit="NOT_ESTABLISHED")
