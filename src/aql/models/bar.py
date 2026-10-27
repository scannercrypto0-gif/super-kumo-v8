"""
AQL MarketBar model — G1-WP01-MVP
Aligns with 09_DATA_SCHEMAS.md: symbol, interval, bar_close, bar_open, OHLCV,
is_final, ingested_at, source.
State labels per execution order:
  RECEIVED → LOCAL_COMMITTED → PERSISTED → RECOVERED → UNRESOLVED_DATA_GAP
"""
from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, asdict
from enum import Enum
from typing import Optional


class BarState(str, Enum):
    RECEIVED = "RECEIVED"
    LOCAL_COMMITTED = "LOCAL_COMMITTED"
    PERSISTED = "PERSISTED"
    RECOVERED = "RECOVERED"
    UNRESOLVED_DATA_GAP = "UNRESOLVED_DATA_GAP"


@dataclass
class MarketBar:
    """
    Canonical G1 MarketBar.
    Only bars with is_final=True and bar_close <= decision_cutoff are usable
    for decision-making (G0-TIME-01 / 09_DATA_SCHEMAS.md).
    """
    # Identity
    symbol: str          # e.g. "BTCUSDT"
    interval: str        # e.g. "1m"
    bar_open: int        # kline open time — ms epoch UTC (Binance: k.t)
    bar_close: int       # kline close time — ms epoch UTC (Binance: k.T)

    # OHLCV
    open: float
    high: float
    low: float
    close: float
    volume: float

    # Temporal integrity (TIME-01)
    is_final: bool       # Binance k.x — True only when the bar is complete
    source: str          # "binance_ws" | "binance_rest_recovery"
    ingested_at: int     # local wall-clock when message was received — ms epoch UTC
    committed_at: Optional[int] = None  # LEGACY pre-COMMIT attempt marker; not completion proof.
    # New completion evidence is a separate Core journal receipt; wire fields/checksum unchanged.

    # Pipeline state
    state: BarState = BarState.RECEIVED

    # Integrity
    checksum: Optional[str] = None  # SHA-256 of canonical fields

    def stable_key(self) -> str:
        """Stable idempotency key: symbol + interval + bar_open (unique per bar)."""
        return f"{self.symbol}:{self.interval}:{self.bar_open}"

    def compute_checksum(self) -> str:
        """SHA-256 over canonical payload fields (excluding state/timestamps)."""
        payload = {
            "symbol": self.symbol,
            "interval": self.interval,
            "bar_open": self.bar_open,
            "bar_close": self.bar_close,
            "open": self.open,
            "high": self.high,
            "low": self.low,
            "close": self.close,
            "volume": self.volume,
            "is_final": self.is_final,
            "source": self.source,
        }
        return hashlib.sha256(
            json.dumps(payload, sort_keys=True).encode()
        ).hexdigest()

    def with_checksum(self) -> "MarketBar":
        self.checksum = self.compute_checksum()
        return self

    def to_dict(self) -> dict:
        d = asdict(self)
        d["state"] = self.state.value
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "MarketBar":
        d = dict(d)
        d["state"] = BarState(d.get("state", "RECEIVED"))
        return cls(**d)

    @classmethod
    def from_binance_ws_kline(cls, k: dict) -> "MarketBar":
        """
        Parse from Binance WebSocket kline payload (the 'k' sub-object).
        Reference: https://developers.binance.com/docs/binance-spot-api-docs/web-socket-streams#klinecandlestick-streams
        """
        now_ms = int(time.time() * 1000)
        bar = cls(
            symbol=k["s"],
            interval=k["i"],
            bar_open=int(k["t"]),
            bar_close=int(k["T"]),
            open=float(k["o"]),
            high=float(k["h"]),
            low=float(k["l"]),
            close=float(k["c"]),
            volume=float(k["v"]),
            is_final=bool(k["x"]),
            source="binance_ws",
            ingested_at=now_ms,
            state=BarState.RECEIVED,
        )
        return bar.with_checksum()

    @classmethod
    def from_binance_rest_kline(cls, row: list, symbol: str, interval: str) -> "MarketBar":
        """
        Parse from Binance REST /api/v3/klines row.
        Row format: [open_time, open, high, low, close, volume, close_time, ...]
        """
        now_ms = int(time.time() * 1000)
        bar = cls(
            symbol=symbol,
            interval=interval,
            bar_open=int(row[0]),
            bar_close=int(row[6]),
            open=float(row[1]),
            high=float(row[2]),
            low=float(row[3]),
            close=float(row[4]),
            volume=float(row[5]),
            is_final=True,   # REST returns completed bars only
            source="binance_rest_recovery",
            ingested_at=now_ms,
            state=BarState.RECOVERED,
        )
        return bar.with_checksum()
