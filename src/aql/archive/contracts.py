"""Versioned canonical envelopes. Unknown observations are never invented."""
from __future__ import annotations
import hashlib
import json
import math
import re
from ..models.bar import MarketBar


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False).encode("utf-8")


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def parse(raw):
    def pairs(items):
        out = {}
        for key, value in items:
            if key in out:
                raise ValueError("Duplicate JSON key")
            out[key] = value
        return out
    def reject(_):
        raise ValueError("Nonfinite JSON")
    def finite_float(text):
        value = float(text)
        if not math.isfinite(value):
            raise ValueError("Nonfinite JSON")
        return value
    return json.loads(raw, object_pairs_hook=pairs, parse_constant=reject,
                      parse_float=finite_float)


def timestamp(value):
    if type(value) is not int or not 0 <= value < 253402300800000:
        raise ValueError("Expected UTC epoch milliseconds")
    return value


def market_envelope(row, *, journal_id, market, build, policy, cutoff_ms):
    """Record journal timestamps as recorded, NOT a certified fsync completion."""
    bar = MarketBar.from_dict(parse(row["payload_json"]))
    if (type(bar.symbol) is not str or not re.fullmatch(r"[A-Za-z0-9_.-]{1,64}", bar.symbol) or
            type(bar.source) is not str or not 1 <= len(bar.source) <= 160):
        raise ValueError("Explicit bounded source/symbol required")
    if (bar.is_final is not True or bar.checksum not in (None, "", row["checksum"]) or
            bar.compute_checksum() != row["checksum"]):
        raise ValueError("Non-final/corrupt journal bar")
    for field in ("bar_open", "bar_close", "ingested_at"):
        timestamp(getattr(bar, field))
    if bar.committed_at is not None:
        timestamp(bar.committed_at)
        if bar.committed_at < bar.ingested_at:
            raise ValueError("Commit precedes receipt")
    if bar.bar_close < bar.bar_open or bar.bar_close >= cutoff_ms or bar.ingested_at > cutoff_ms:
        raise ValueError("Incomplete/future bar")
    if bar.committed_at is not None and bar.committed_at > cutoff_ms:
        raise ValueError("Future recorded commit")
    for name in ("open", "high", "low", "close", "volume"):
        value = getattr(bar, name)
        if type(value) not in (int, float) or not math.isfinite(value):
            raise ValueError("Invalid numeric OHLCV")
    if (min(bar.open, bar.high, bar.low, bar.close) <= 0 or bar.volume < 0 or
            bar.high < max(bar.open, bar.close, bar.low) or bar.low > min(bar.open, bar.close, bar.high)):
        raise ValueError("Invalid OHLCV geometry")
    from ..recovery.gap_recovery import _binance_interval_ms
    width = _binance_interval_ms(bar.interval)
    if width <= 0 or bar.bar_close != bar.bar_open + width - 1:
        raise ValueError("Invalid interval/close")
    if bar.stable_key() != row["stable_key"]:
        raise ValueError("Journal key mismatch")
    # The G1 journal payload is unchanged by local ACK. Bind the original state.
    value = {"schema": "aql.market-archive.v1", "record_id": bar.stable_key(),
             "journal_id": journal_id, "source_seq": row["id"], "market": market,
             "journal_content_checksum": row["checksum"],
             "build": build, "policy": policy, "utc_unit": "epoch_ms",
             "bar": bar.to_dict(), "times": {
                 "market_close_ms": bar.bar_close, "source_event_ms": None,
                 "receipt_ms": bar.ingested_at, "ingest_ms": bar.ingested_at,
                 "available_ms": None,
                 "availability_lower_bound_ms": max(bar.bar_close + 1, bar.ingested_at),
                 "journal_commit_recorded_ms": bar.committed_at,
                 "fsync_completed_ms": None},
             "availability_kind": "DERIVED_LOWER_BOUND_NOT_CONFIRMED",
             "missing": ["source_event_ms", "available_ms", "fsync_completed_ms"] +
                        (["journal_commit_recorded_ms"] if bar.committed_at is None else []) +
                        (["bar_payload_checksum"] if not bar.checksum else [])}
    return {**value, "envelope_hash": digest(value)}


FEATURES = ("btc_regime", "eth_regime", "breadth", "liquidity", "volatility", "relative_strength")


def decision_context(*, context_id, decision_ms, outcome, strategy_version, policy_version, features):
    """Schema plumbing only; no runtime capture, trader eligibility or execution."""
    timestamp(decision_ms)
    if outcome not in ("ACCEPTED", "REJECTED", "EXPIRED", "NO_FILL"):
        raise ValueError("Explicit outcome required")
    if any(type(v) is not str or not v for v in (context_id, strategy_version, policy_version)):
        raise ValueError("Explicit identity/versions required")
    if set(features) != set(FEATURES):
        raise ValueError("Complete feature inventory, including unavailable fields, required")
    for value in features.values():
        if set(value) != {"value", "source", "version", "event_ms", "receipt_ms", "available_ms", "freshness_ms", "status"}:
            raise ValueError("Incomplete feature provenance")
        if value["status"] == "UNAVAILABLE":
            if any(value[k] is not None for k in value if k != "status"):
                raise ValueError("Unavailable context must not fabricate metadata")
        elif value["status"] == "AVAILABLE":
            for key in ("event_ms", "receipt_ms", "available_ms"):
                timestamp(value[key])
            timestamp(value["freshness_ms"])
            if (any(type(value[k]) is not str or not 1 <= len(value[k]) <= 160 for k in ("source", "version")) or value["value"] is None or
                    value["available_ms"] < max(value["event_ms"], value["receipt_ms"]) or
                    value["available_ms"] > decision_ms or
                    value["freshness_ms"] != decision_ms - value["available_ms"]):
                raise ValueError("Future/inconsistent feature evidence")
        else:
            raise ValueError("Explicit availability required")
    data = {"schema": "aql.pit-context.v1", "context_id": context_id, "decision_ms": decision_ms,
            "outcome": outcome, "strategy_version": strategy_version,
            "policy_version": policy_version, "features": features}
    return canonical({**data, "context_hash": digest(data)})
