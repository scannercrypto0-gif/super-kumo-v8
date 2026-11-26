"""G2 — Universe snapshot and market eligibility classification.

Classifies every symbol in the provided inventory into exactly one of:
  ELIGIBLE     — passes all filters; may be nominated
  REJECTED     — fails one or more hard eligibility rules
  MISSING      — required data field is absent
  UNSUPPORTED  — market type or quote asset not in scope
  UNKNOWN      — cannot be determined (data error)

Rotating deterministic selection (fair across full eligible set):
  select_candidates(universe, limit, offset) — offset rotates across alphabetically
  sorted eligible symbols so no symbol is perpetually skipped.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Sequence

from .contracts import _utc, _decimal, canonical_bytes, sha256_hex

# ── Eligibility policy constants ───────────────────────────────────────────────

MIN_QUOTE_VOLUME_24H = Decimal("5_000_000")   # minimum 24h quote volume (USDT)
MAX_SPREAD_BPS = Decimal("30")                # maximum bid/ask spread in basis points
REQUIRED_QUOTE_ASSET = "USDT"
REQUIRED_TRADING_STATUS = "TRADING"

# ── Classification codes ───────────────────────────────────────────────────────

STATUS_ELIGIBLE = "ELIGIBLE"
STATUS_REJECTED = "REJECTED"
STATUS_MISSING = "MISSING"
STATUS_UNSUPPORTED = "UNSUPPORTED"
STATUS_UNKNOWN = "UNKNOWN"

ALL_STATUSES = frozenset({STATUS_ELIGIBLE, STATUS_REJECTED, STATUS_MISSING,
                          STATUS_UNSUPPORTED, STATUS_UNKNOWN})


# ── Market snapshot (input from caller) ───────────────────────────────────────

@dataclass(frozen=True)
class MarketInfo:
    """Minimal market metadata supplied by the caller for eligibility evaluation.

    observed_at  — wall-clock time when this snapshot was recorded.  Must be ≤ cutoff.
    """
    symbol: str
    quote_asset: str
    spot_enabled: bool
    trading_status: str
    quote_volume_24h: Decimal
    bid: Decimal
    ask: Decimal
    observed_at: datetime

    def __post_init__(self) -> None:
        object.__setattr__(self, "observed_at", _utc(self.observed_at))
        for f in ("quote_volume_24h", "bid", "ask"):
            object.__setattr__(self, f, _decimal(getattr(self, f)))


# ── Universe item ──────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class UniverseItem:
    symbol: str
    status: str
    reasons: tuple[str, ...]
    cohort: str          # "BASELINE" | "LOW_LIQUIDITY" | "EXCLUDED" | "UNSUPPORTED"
    market: MarketInfo | None

    def as_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "status": self.status,
            "reasons": list(self.reasons),
            "cohort": self.cohort,
            "market": {
                "symbol": self.market.symbol,
                "quote_asset": self.market.quote_asset,
                "spot_enabled": self.market.spot_enabled,
                "trading_status": self.market.trading_status,
                "quote_volume_24h": str(self.market.quote_volume_24h),
                "bid": str(self.market.bid),
                "ask": str(self.market.ask),
                "observed_at": self.market.observed_at.isoformat(),
            } if self.market is not None else None,
        }


# ── Universe snapshot ──────────────────────────────────────────────────────────

@dataclass(frozen=True)
class UniverseSnapshot:
    """Immutable snapshot of the full market inventory at a given cutoff.

    snapshot_id  — opaque identity (SHA-256 of canonical payload)
    cutoff_at    — decision cutoff; no symbol observed after this is included
    """
    cutoff_at: datetime
    items: tuple[UniverseItem, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "cutoff_at", _utc(self.cutoff_at))

    @property
    def eligible(self) -> list[UniverseItem]:
        return [x for x in self.items if x.status == STATUS_ELIGIBLE]

    @property
    def snapshot_id(self) -> str:
        return sha256_hex(canonical_bytes(self._payload()))

    def _payload(self) -> dict:
        return {
            "cutoff_at": self.cutoff_at.isoformat(),
            "items": [x.as_dict() for x in sorted(self.items, key=lambda i: i.symbol)],
        }

    def summary(self) -> dict:
        from collections import Counter
        status_counts = dict(Counter(x.status for x in self.items))
        cohort_counts = dict(Counter(x.cohort for x in self.items))
        return {
            "cutoff_at": self.cutoff_at.isoformat(),
            "total": len(self.items),
            "eligible_count": len(self.eligible),
            "status_counts": status_counts,
            "cohort_counts": cohort_counts,
            "eligible_symbols": sorted(x.symbol for x in self.eligible),
            "snapshot_id": self.snapshot_id,
        }


# ── Eligibility logic ──────────────────────────────────────────────────────────

def _spread_bps(bid: Decimal, ask: Decimal) -> Decimal | None:
    if bid <= 0 or ask <= 0 or ask < bid:
        return None
    return Decimal("10000") * (ask - bid) / ((ask + bid) / 2)


def classify_symbol(market: MarketInfo, cutoff_at: datetime) -> UniverseItem:
    """Classify a single symbol against eligibility policy at cutoff_at.

    A snapshot observed *after* the cutoff cannot inform any eligibility decision
    (fail-closed PIT rule: reject as UNKNOWN, expose no features).
    """
    cutoff_at = _utc(cutoff_at)
    symbol = market.symbol

    # PIT check — snapshot must have been recorded before or at cutoff
    if market.observed_at > cutoff_at:
        return UniverseItem(symbol, STATUS_UNKNOWN,
                            ("MARKET_SNAPSHOT_FROM_FUTURE",), "EXCLUDED", None)

    # Quote asset / naming check
    if market.quote_asset != REQUIRED_QUOTE_ASSET or not symbol.endswith(REQUIRED_QUOTE_ASSET):
        return UniverseItem(symbol, STATUS_UNSUPPORTED,
                            ("NOT_USDT_PAIR",), "UNSUPPORTED", market)

    # Hard eligibility gates
    reasons: list[str] = []
    if not market.spot_enabled or market.trading_status != REQUIRED_TRADING_STATUS:
        reasons.append("SPOT_NOT_TRADABLE")
    if market.quote_volume_24h < MIN_QUOTE_VOLUME_24H:
        reasons.append("LOW_24H_QUOTE_VOLUME")
    spread = _spread_bps(market.bid, market.ask)
    if spread is None:
        reasons.append("INVALID_BID_ASK")
    elif spread > MAX_SPREAD_BPS:
        reasons.append("SPREAD_ABOVE_LIMIT")

    cohort = "BASELINE"
    if "LOW_24H_QUOTE_VOLUME" in reasons:
        cohort = "LOW_LIQUIDITY"
    if reasons:
        return UniverseItem(symbol, STATUS_REJECTED, tuple(reasons), cohort, market)
    return UniverseItem(symbol, STATUS_ELIGIBLE, (), cohort, market)


def build_universe_snapshot(
    markets: Sequence[MarketInfo],
    cutoff_at: datetime,
) -> UniverseSnapshot:
    """Classify all provided markets and return an immutable snapshot."""
    cutoff_at = _utc(cutoff_at)
    items = tuple(classify_symbol(m, cutoff_at) for m in markets)
    return UniverseSnapshot(cutoff_at=cutoff_at, items=items)


# ── Deterministic rotating selection ──────────────────────────────────────────

def select_candidates(
    snapshot: UniverseSnapshot,
    limit: int,
    offset: int,
) -> tuple[UniverseItem, ...]:
    """Select up to `limit` eligible symbols using a rotating deterministic offset.

    Alphabetically sorted eligible list; rotating offset ensures fairness over
    multiple scanner runs without fixed favorites.
    """
    if not isinstance(limit, int) or isinstance(limit, bool) or limit < 1:
        raise ValueError("LIMIT_MUST_BE_POSITIVE_INT")
    if not isinstance(offset, int) or isinstance(offset, bool) or offset < 0:
        raise ValueError("OFFSET_MUST_BE_NON_NEGATIVE_INT")

    eligible = sorted(snapshot.eligible, key=lambda x: x.symbol)
    n = len(eligible)
    if n == 0:
        return ()
    count = min(limit, n)
    start = offset % n
    return tuple(eligible[(start + i) % n] for i in range(count))
