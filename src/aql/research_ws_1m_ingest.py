"""Bounded offline adapter for original finalized Binance 1m websocket kline frames.

A frame supplied by a separately authorized collector is validated and persisted.
No socket, network access, host task modification, or trading authority.
"""
from __future__ import annotations

import hashlib
import json

from aql.research_timeframes import MINUTE
from aql.research_bar_store import ResearchBarStore


def ingest_closed_1m_frame(store: ResearchBarStore, raw: bytes, *,
                           received_at_ms: int, expected_symbol="BTCUSDT"):
    if type(raw) is not bytes or not 0 < len(raw) <= 65536:
        raise ValueError("FRAME_BOUND")
    if type(received_at_ms) is not int or received_at_ms < 0:
        raise ValueError("RECEIPT_CLOCK_REQUIRED")

    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("DUPLICATE_JSON_KEY")
            result[key] = value
        return result

    try:
        frame = json.loads(raw, object_pairs_hook=unique)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("FRAME_INVALID") from exc
    if type(frame) is not dict or frame.get("e") != "kline" or type(frame.get("k")) is not dict:
        raise ValueError("BINANCE_KLINE_REQUIRED")
    candle = frame["k"]
    if (frame.get("s") != expected_symbol or candle.get("s") != expected_symbol
            or candle.get("i") != "1m"):
        raise ValueError("FOREIGN_KLINE")
    if candle.get("x") is not True:
        raise ValueError("PROVISIONAL_KLINE")
    opened, closed = candle.get("t"), candle.get("T")
    if (type(opened) is not int or opened < 0 or opened % MINUTE
            or type(closed) is not int or closed != opened + MINUTE - 1):
        raise ValueError("KLINE_GRID_INVALID")
    if received_at_ms < opened + MINUTE:
        raise ValueError("RECEIVED_BEFORE_FINALITY")
    event_time = frame.get("E")
    if type(event_time) is not int or event_time < opened + MINUTE - 1 or event_time > received_at_ms:
        raise ValueError("EVENT_CLOCK_INVALID")
    bar = {
        "symbol": expected_symbol, "interval": "1m", "open_ms": opened, "final": True,
        "o": candle.get("o"), "h": candle.get("h"), "l": candle.get("l"),
        "c": candle.get("c"), "v": candle.get("v"),
        "source_sha256": hashlib.sha256(raw).hexdigest(),
        "available_at_ms": received_at_ms,
    }
    result = store.insert_1m(bar, source_class="FORWARD_UNQUALIFIED")
    return {"status": "FORWARD_UNQUALIFIED_PERSISTED",
            "symbol": expected_symbol, "open_ms": opened,
            "bar_sha256": result["sha256"], "source_sha256": bar["source_sha256"],
            "source_authenticity": "NOT_INDEPENDENTLY_ATTESTED",
            "trading_authority": "NONE"}
