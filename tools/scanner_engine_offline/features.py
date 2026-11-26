"""G3 — Multi-timeframe (MTF) feature computation.

All features are computed from admitted bars only (PIT-clean, close_at ≤ cutoff).
Missing bars → SCORE_UNAVAILABLE on the affected feature; never silently omit.

Supported timeframes and parent/child alignment:
  CHILD_PARENT = {"30m": ("5m", 6), "4h": ("1h", 4)}
  Standalone: "5m", "1h", "1d", "1w"

RVOL variants:
  rvol_base  = last bar base_volume  / mean(prior 20 bars base_volume)
  rvol_quote = last bar quote_volume / mean(prior 20 bars quote_volume)

RVOL requires exactly 21 bars (1 current + 20 prior).  Fewer → SCORE_UNAVAILABLE.

Coverage report:
  For each feature: {status: "OK"|"UNAVAILABLE", reason: str|None}
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, ROUND_HALF_EVEN
from typing import Sequence

from .contracts import AdmittedBar, _utc, _decimal

# ── MTF alignment config ───────────────────────────────────────────────────────

CHILD_PARENT: dict[str, tuple[str, int]] = {
    "30m": ("5m", 6),
    "4h": ("1h", 4),
}

SUPPORTED_TIMEFRAMES = frozenset({"5m", "30m", "1h", "4h", "1d", "1w"})
RVOL_WINDOW = 20          # prior bars needed for RVOL denominator
RVOL_REQUIRED = RVOL_WINDOW + 1  # total bars (prior + current)
SPREAD_PRECISION = Decimal("0.01")  # rounding unit for spread_bps

# ── Feature status codes ───────────────────────────────────────────────────────

STATUS_OK = "OK"
STATUS_UNAVAILABLE = "SCORE_UNAVAILABLE"

# Reason codes
REASON_INSUFFICIENT_BARS = "INSUFFICIENT_BARS"
REASON_INVALID_PRICE = "INVALID_PRICE"
REASON_INVALID_VOLUME = "INVALID_VOLUME"
REASON_ZERO_DENOMINATOR = "ZERO_DENOMINATOR"
REASON_MISSING_TIMEFRAME = "MISSING_TIMEFRAME"
REASON_RECONCILIATION_FAILED = "RECONCILIATION_FAILED"


# ── Feature cell ───────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class FeatureCell:
    """A single computed feature value with provenance."""
    name: str
    timeframe: str
    status: str
    value: str | None    # str(Decimal) or None
    reason: str | None   # set when status == SCORE_UNAVAILABLE

    @property
    def is_ok(self) -> bool:
        return self.status == STATUS_OK

    def as_dict(self) -> dict:
        return {
            "name": self.name,
            "timeframe": self.timeframe,
            "status": self.status,
            "value": self.value,
            "reason": self.reason,
        }


def _ok(name: str, timeframe: str, value: Decimal) -> FeatureCell:
    return FeatureCell(name, timeframe, STATUS_OK, str(value), None)


def _unavailable(name: str, timeframe: str, reason: str) -> FeatureCell:
    return FeatureCell(name, timeframe, STATUS_UNAVAILABLE, None, reason)


# ── MTF feature snapshot ───────────────────────────────────────────────────────

@dataclass(frozen=True)
class MTFFeatureSnapshot:
    """All computed features for one symbol at one cutoff.

    features   — ordered tuple of FeatureCell
    coverage   — dict mapping feature name → {status, reason}
    ok_count   — number of features with STATUS_OK
    total      — total feature count
    """
    symbol: str
    cutoff_at: datetime
    features: tuple[FeatureCell, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "cutoff_at", _utc(self.cutoff_at))

    @property
    def ok_count(self) -> int:
        return sum(1 for f in self.features if f.is_ok)

    @property
    def total(self) -> int:
        return len(self.features)

    @property
    def coverage_ratio(self) -> Decimal:
        if self.total == 0:
            return Decimal("0")
        return Decimal(self.ok_count) / Decimal(self.total)

    def as_snapshot_dict(self) -> dict:
        """Feature name → value string (None if unavailable). Used in envelope."""
        return {f.name: f.value for f in self.features}

    def coverage_dict(self) -> dict:
        return {
            "ok": self.ok_count,
            "total": self.total,
            "ratio": str(self.coverage_ratio.quantize(Decimal("0.0001"))),
            "features": {f.name: {"status": f.status, "reason": f.reason}
                         for f in self.features},
        }

    def as_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "cutoff_at": self.cutoff_at.isoformat(),
            "features": [f.as_dict() for f in self.features],
            "coverage": self.coverage_dict(),
        }


# ── Low-level numeric helpers ──────────────────────────────────────────────────

def _mean(values: Sequence[Decimal]) -> Decimal | None:
    if not values:
        return None
    s = sum(values, Decimal(0))
    return s / Decimal(len(values))


def _rvol(bars: Sequence[AdmittedBar], name: str, timeframe: str,
          *, volume_attr: str) -> FeatureCell:
    """Compute RVOL for a given volume attribute (base_volume or quote_volume)."""
    if len(bars) < RVOL_REQUIRED:
        return _unavailable(name, timeframe, REASON_INSUFFICIENT_BARS)
    # Use last RVOL_REQUIRED bars (sorted ascending; last is current)
    window = bars[-RVOL_REQUIRED:]
    current = getattr(window[-1], volume_attr)
    prior = [getattr(b, volume_attr) for b in window[:-1]]
    mean_prior = _mean(prior)
    if mean_prior is None or mean_prior == 0:
        return _unavailable(name, timeframe, REASON_ZERO_DENOMINATOR)
    ratio = (current / mean_prior).quantize(Decimal("0.0001"), rounding=ROUND_HALF_EVEN)
    return _ok(name, timeframe, ratio)


def _c2c_pct(bars: Sequence[AdmittedBar], name: str, timeframe: str,
             lookback: int = 1) -> FeatureCell:
    """Close-to-close momentum over `lookback` bars."""
    if len(bars) < lookback + 1:
        return _unavailable(name, timeframe, REASON_INSUFFICIENT_BARS)
    prev_close = bars[-(lookback + 1)].close
    curr_close = bars[-1].close
    if prev_close <= 0:
        return _unavailable(name, timeframe, REASON_INVALID_PRICE)
    pct = ((curr_close - prev_close) / prev_close * 100).quantize(
        Decimal("0.0001"), rounding=ROUND_HALF_EVEN)
    return _ok(name, timeframe, pct)


def _oc_pct(bars: Sequence[AdmittedBar], name: str, timeframe: str) -> FeatureCell:
    """Open-to-close momentum for the last bar."""
    if not bars:
        return _unavailable(name, timeframe, REASON_INSUFFICIENT_BARS)
    bar = bars[-1]
    if bar.open <= 0:
        return _unavailable(name, timeframe, REASON_INVALID_PRICE)
    pct = ((bar.close - bar.open) / bar.open * 100).quantize(
        Decimal("0.0001"), rounding=ROUND_HALF_EVEN)
    return _ok(name, timeframe, pct)


def _atr_pct(bars: Sequence[AdmittedBar], name: str, timeframe: str,
             period: int = 14) -> FeatureCell:
    """ATR as percentage of close (volatility proxy)."""
    if len(bars) < period + 1:
        return _unavailable(name, timeframe, REASON_INSUFFICIENT_BARS)
    trs: list[Decimal] = []
    window = bars[-(period + 1):]
    for i in range(1, len(window)):
        b = window[i]
        prev_close = window[i - 1].close
        if prev_close <= 0 or b.close <= 0:
            return _unavailable(name, timeframe, REASON_INVALID_PRICE)
        tr = max(b.high - b.low, abs(b.high - prev_close), abs(b.low - prev_close))
        trs.append(tr)
    atr = _mean(trs)
    if atr is None:
        return _unavailable(name, timeframe, REASON_INSUFFICIENT_BARS)
    last_close = bars[-1].close
    if last_close <= 0:
        return _unavailable(name, timeframe, REASON_INVALID_PRICE)
    atr_pct = (atr / last_close * 100).quantize(Decimal("0.0001"), rounding=ROUND_HALF_EVEN)
    return _ok(name, timeframe, atr_pct)


def _trend_slope(bars: Sequence[AdmittedBar], name: str, timeframe: str,
                 period: int = 10) -> FeatureCell:
    """Linear regression slope of close prices, normalised by mean close."""
    if len(bars) < period:
        return _unavailable(name, timeframe, REASON_INSUFFICIENT_BARS)
    window = bars[-period:]
    closes = [b.close for b in window]
    if any(c <= 0 for c in closes):
        return _unavailable(name, timeframe, REASON_INVALID_PRICE)
    n = Decimal(len(closes))
    x_mean = (n - 1) / 2
    y_mean = _mean(closes)
    if y_mean is None or y_mean == 0:
        return _unavailable(name, timeframe, REASON_ZERO_DENOMINATOR)
    num = sum((Decimal(i) - x_mean) * (closes[i] - y_mean) for i in range(len(closes)))
    den = sum((Decimal(i) - x_mean) ** 2 for i in range(len(closes)))
    if den == 0:
        return _unavailable(name, timeframe, REASON_ZERO_DENOMINATOR)
    slope = (num / den) / y_mean * 100  # normalised % per bar
    slope = slope.quantize(Decimal("0.0001"), rounding=ROUND_HALF_EVEN)
    return _ok(name, timeframe, slope)


def _range_position(bars: Sequence[AdmittedBar], name: str, timeframe: str,
                    lookback: int = 20) -> FeatureCell:
    """Last close position within lookback high-low range [0–100%]."""
    if len(bars) < lookback:
        return _unavailable(name, timeframe, REASON_INSUFFICIENT_BARS)
    window = bars[-lookback:]
    high = max(b.high for b in window)
    low = min(b.low for b in window)
    last_close = bars[-1].close
    if high <= low or low <= 0:
        return _unavailable(name, timeframe, REASON_INVALID_PRICE)
    pos = ((last_close - low) / (high - low) * 100).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_EVEN)
    return _ok(name, timeframe, pos)


def _spread_bps_feature(bid: Decimal, ask: Decimal, name: str, timeframe: str) -> FeatureCell:
    if bid <= 0 or ask <= 0 or ask < bid:
        return _unavailable(name, timeframe, REASON_INVALID_PRICE)
    mid = (bid + ask) / 2
    if mid == 0:
        return _unavailable(name, timeframe, REASON_ZERO_DENOMINATOR)
    spread = (Decimal("10000") * (ask - bid) / mid).quantize(
        SPREAD_PRECISION, rounding=ROUND_HALF_EVEN)
    return _ok(name, timeframe, spread)


# ── MTF feature computation ────────────────────────────────────────────────────

def compute_features(
    symbol: str,
    cutoff_at: datetime,
    bars_by_tf: dict[str, Sequence[AdmittedBar]],
    bid: Decimal | None = None,
    ask: Decimal | None = None,
) -> MTFFeatureSnapshot:
    """Compute the full MTF feature set for one symbol at cutoff_at.

    bars_by_tf — timeframe → list of AdmittedBar (must be pre-PIT-admitted, asc sorted)
    bid / ask  — optional market microstructure snapshot for spread features
    """
    cutoff_at = _utc(cutoff_at)
    cells: list[FeatureCell] = []

    def bars(tf: str) -> Sequence[AdmittedBar]:
        return bars_by_tf.get(tf, [])

    # ── 5m features ───────────────────────────────────────────────────────────
    b5 = bars("5m")
    cells.append(_rvol(b5,  "rvol_base_5m",  "5m", volume_attr="base_volume"))
    cells.append(_rvol(b5,  "rvol_quote_5m", "5m", volume_attr="quote_volume"))
    cells.append(_c2c_pct(b5, "c2c_1bar_5m",  "5m", lookback=1))
    cells.append(_oc_pct(b5,  "oc_5m",        "5m"))
    cells.append(_atr_pct(b5, "atr_pct_5m",   "5m", period=14))
    cells.append(_range_position(b5, "range_pos_5m", "5m", lookback=20))

    # ── 30m features ──────────────────────────────────────────────────────────
    b30 = bars("30m")
    cells.append(_rvol(b30,  "rvol_base_30m",  "30m", volume_attr="base_volume"))
    cells.append(_rvol(b30,  "rvol_quote_30m", "30m", volume_attr="quote_volume"))
    cells.append(_c2c_pct(b30, "c2c_1bar_30m",  "30m", lookback=1))
    cells.append(_oc_pct(b30,  "oc_30m",        "30m"))
    cells.append(_atr_pct(b30, "atr_pct_30m",   "30m", period=14))
    cells.append(_trend_slope(b30, "trend_slope_30m", "30m", period=10))

    # ── 1h features ───────────────────────────────────────────────────────────
    b1h = bars("1h")
    cells.append(_rvol(b1h,  "rvol_base_1h",  "1h", volume_attr="base_volume"))
    cells.append(_rvol(b1h,  "rvol_quote_1h", "1h", volume_attr="quote_volume"))
    cells.append(_c2c_pct(b1h, "c2c_1bar_1h",  "1h", lookback=1))
    cells.append(_oc_pct(b1h,  "oc_1h",        "1h"))
    cells.append(_atr_pct(b1h, "atr_pct_1h",   "1h", period=14))
    cells.append(_trend_slope(b1h, "trend_slope_1h", "1h", period=10))
    cells.append(_range_position(b1h, "range_pos_1h", "1h", lookback=20))

    # ── 4h features ───────────────────────────────────────────────────────────
    b4h = bars("4h")
    cells.append(_rvol(b4h,  "rvol_base_4h",  "4h", volume_attr="base_volume"))
    cells.append(_rvol(b4h,  "rvol_quote_4h", "4h", volume_attr="quote_volume"))
    cells.append(_c2c_pct(b4h, "c2c_1bar_4h",  "4h", lookback=1))
    cells.append(_oc_pct(b4h,  "oc_4h",        "4h"))
    cells.append(_atr_pct(b4h, "atr_pct_4h",   "4h", period=14))
    cells.append(_trend_slope(b4h, "trend_slope_4h", "4h", period=10))
    cells.append(_range_position(b4h, "range_pos_4h", "4h", lookback=20))

    # ── 1d features ───────────────────────────────────────────────────────────
    b1d = bars("1d")
    cells.append(_c2c_pct(b1d, "c2c_1bar_1d", "1d", lookback=1))
    cells.append(_trend_slope(b1d, "trend_slope_1d", "1d", period=10))
    cells.append(_range_position(b1d, "range_pos_1d", "1d", lookback=20))

    # ── Liquidity / spread (market microstructure) ────────────────────────────
    if bid is not None and ask is not None:
        cells.append(_spread_bps_feature(bid, ask, "spread_bps", "market"))
    else:
        cells.append(_unavailable("spread_bps", "market", "BID_ASK_NOT_PROVIDED"))

    return MTFFeatureSnapshot(
        symbol=symbol,
        cutoff_at=cutoff_at,
        features=tuple(cells),
    )
