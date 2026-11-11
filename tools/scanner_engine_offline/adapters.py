"""G6 — ATLAS compatibility adapters and synthetic fixture builders.

Bridges the scanner engine to the ATLAS output contract (ScannerNominationEnvelope)
and provides deterministic synthetic fixtures for offline tests — no network calls.

Fixture generators:
  make_synthetic_bars()     — deterministic OHLCV bars for any timeframe/symbol
  make_synthetic_market()   — deterministic MarketInfo for any symbol
  make_synthetic_universe() — full snapshot with configurable eligible/rejected mix

Adapter:
  candidate_to_envelope()   — ScanCandidate + MTFFeatureSnapshot → ScannerNominationEnvelope
"""
from __future__ import annotations

import hashlib
import math
from datetime import datetime, timezone, timedelta
from decimal import Decimal

from .contracts import (
    AdmittedBar, SourceManifest, ScannerNominationEnvelope,
    AVAILABILITY_RETRO, SCHEMA_VERSION, _utc,
)
from .universe import MarketInfo, UniverseSnapshot, build_universe_snapshot
from .features import MTFFeatureSnapshot
from .screening import ScanCandidate

UTC = timezone.utc

# ── Deterministic synthetic data factories ────────────────────────────────────

_TF_MINUTES: dict[str, int] = {
    "5m": 5, "30m": 30, "1h": 60, "4h": 240, "1d": 1440, "1w": 10080,
}


def _symbol_seed(symbol: str) -> int:
    """Deterministic integer seed from symbol string."""
    return int(hashlib.sha256(symbol.encode()).hexdigest()[:8], 16)


def make_synthetic_bars(
    symbol: str,
    timeframe: str,
    cutoff_at: datetime,
    count: int = 30,
    source_id: str = "SYNTHETIC-FIXTURE-V1",
) -> list[AdmittedBar]:
    """Generate `count` deterministic OHLCV bars ending at or before cutoff_at.

    Bars are fully PIT-valid (close_at ≤ cutoff_at, available_at = close_at).
    Prices follow a deterministic pseudo-random walk seeded by (symbol, timeframe).
    """
    cutoff_at = _utc(cutoff_at)
    tf_min = _TF_MINUTES.get(timeframe)
    if tf_min is None:
        raise ValueError(f"UNSUPPORTED_TIMEFRAME:{timeframe}")
    step = timedelta(minutes=tf_min)

    # Walk backward from the last complete bar before cutoff
    bar_duration = step
    last_close = cutoff_at - timedelta(seconds=1)
    # Align to bar boundary
    epoch = datetime(2020, 1, 1, tzinfo=UTC)
    elapsed = int((last_close - epoch).total_seconds() // bar_duration.total_seconds())
    last_bar_close = epoch + timedelta(seconds=(elapsed + 1) * bar_duration.total_seconds())
    if last_bar_close > cutoff_at:
        last_bar_close -= bar_duration

    # P1-01 fix: hash() is NOT stable across Python processes (PYTHONHASHSEED).
    # Use SHA-256 of the timeframe bytes for a stable, cross-process seed.
    tf_seed = int(hashlib.sha256(timeframe.encode()).hexdigest()[:8], 16)
    seed = _symbol_seed(symbol) ^ tf_seed
    bars: list[AdmittedBar] = []
    base_price = Decimal("100") + Decimal(seed % 900)  # 100–999
    vol_base_multiplier = Decimal("1000") + Decimal(seed % 9000)

    for i in range(count - 1, -1, -1):
        close_at = last_bar_close - i * bar_duration
        open_at = close_at - bar_duration
        if close_at > cutoff_at:
            continue

        # Deterministic pseudo-random OHLCV (no randomness — fully reproducible)
        bar_index = elapsed - i
        phase = math.sin(bar_index * 0.31 + seed * 0.001)
        trend = bar_index * Decimal("0.01")
        price_level = base_price + Decimal(str(round(phase * 5, 4))) + trend
        if price_level <= 0:
            price_level = base_price

        open_p = price_level.quantize(Decimal("0.0001"))
        close_p = (price_level * (1 + Decimal(str(round(phase * 0.01, 6))))).quantize(Decimal("0.0001"))
        high_p = max(open_p, close_p) * Decimal("1.002")
        low_p = min(open_p, close_p) * Decimal("0.998")
        if low_p <= 0:
            low_p = Decimal("0.0001")
        base_vol = (vol_base_multiplier * (1 + abs(Decimal(str(phase))))).quantize(Decimal("0.0001"))
        quote_vol = (base_vol * price_level).quantize(Decimal("0.0001"))

        available_at = close_at  # synthetic data: available exactly at close

        bars.append(AdmittedBar(
            source_id=source_id,
            timeframe=timeframe,
            symbol=symbol,
            open_at=open_at,
            close_at=close_at,
            available_at=available_at,
            open=open_p,
            high=high_p.quantize(Decimal("0.0001")),
            low=low_p.quantize(Decimal("0.0001")),
            close=close_p,
            base_volume=base_vol,
            quote_volume=quote_vol,
        ))

    return sorted(bars, key=lambda b: b.open_at)


def make_synthetic_market(
    symbol: str,
    cutoff_at: datetime,
    eligible: bool = True,
) -> MarketInfo:
    """Generate a deterministic MarketInfo for a symbol at cutoff_at."""
    cutoff_at = _utc(cutoff_at)
    seed = _symbol_seed(symbol)
    base_price = Decimal("100") + Decimal(seed % 900)
    spread_frac = Decimal("0.0002") if eligible else Decimal("0.005")
    bid = (base_price * (1 - spread_frac / 2)).quantize(Decimal("0.0001"))
    ask = (base_price * (1 + spread_frac / 2)).quantize(Decimal("0.0001"))
    vol_24h = Decimal("20_000_000") if eligible else Decimal("500_000")
    return MarketInfo(
        symbol=symbol,
        quote_asset="USDT",
        spot_enabled=True,
        trading_status="TRADING",
        quote_volume_24h=vol_24h,
        bid=bid,
        ask=ask,
        observed_at=cutoff_at - timedelta(seconds=30),
    )


def make_synthetic_universe(
    symbols: list[str],
    cutoff_at: datetime,
    ineligible_symbols: list[str] | None = None,
) -> UniverseSnapshot:
    """Generate a deterministic UniverseSnapshot for a list of symbols."""
    ineligible_set = set(ineligible_symbols or [])
    markets = [
        make_synthetic_market(s, cutoff_at, eligible=(s not in ineligible_set))
        for s in symbols
    ]
    return build_universe_snapshot(markets, cutoff_at)


# ── ATLAS envelope adapter ────────────────────────────────────────────────────

def candidate_to_envelope(
    candidate: ScanCandidate,
    feature_snapshot: MTFFeatureSnapshot,
    source_manifest: SourceManifest,
    scanner_id: str,
    market: str = "BINANCE:SPOT:USDT",
) -> ScannerNominationEnvelope:
    """Convert a screened ScanCandidate into a sealed ScannerNominationEnvelope.

    The envelope is content-addressed (digest sealed at creation).
    publishable and delivery_authorized are always False (research output only).
    """
    candidate_id = f"{candidate.symbol}:{candidate.cutoff_at.isoformat()}"
    env = ScannerNominationEnvelope(
        scanner_id=scanner_id,
        candidate_id=candidate_id,
        profile_id=candidate.profile,
        market=market,
        cutoff_at=candidate.cutoff_at,
        availability_class=AVAILABILITY_RETRO,
        stage=candidate.stage,
        source_manifest=source_manifest.as_dict(),
        feature_snapshot=feature_snapshot.as_snapshot_dict(),
        reasons=list(candidate.reasons),
        coverage=feature_snapshot.coverage_dict(),
        score=str(candidate.score) if candidate.score is not None else None,
        score_status=candidate.score_status,
        publishable=False,
        delivery_authorized=False,
    )
    env.seal()
    return env
