"""G7 demo — Offline scanner engine synthetic demo entry point.

Zero network calls.  All data is generated deterministically from symbol names.
Run from the repo root:

    python -m tools.scanner_engine_offline.demo

Output: JSON summary printed to stdout.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone, timedelta

from .contracts import SourceManifest, AVAILABILITY_RETRO, sha256_hex, canonical_bytes
from .universe import build_universe_snapshot
from .engine import OfflineScannerEngine, ScanRunConfig
from .adapters import (
    make_synthetic_bars, make_synthetic_market, make_synthetic_universe,
)

UTC = timezone.utc

# ── Demo configuration ────────────────────────────────────────────────────────

DEMO_SYMBOLS = [
    "SOLUSDT", "AVAXUSDT", "DOTUSDT", "LINKUSDT", "MATICUSDT",
    "ADAUSDT",  "ATOMUSDT", "LTCUSDT", "XRPUSDT",  "BNBUSDT",
    "AAVEUSDT", "UNIUSDT",  "SHIBUSDT", "TRXUSDT",  "NEARUSDT",
]
DEMO_INELIGIBLE = ["SHIBUSDT"]   # low liquidity for demo
DEMO_CUTOFF = datetime(2024, 10, 15, 12, 0, 0, tzinfo=UTC)
DEMO_SCANNER_ID = "AQL-DEMO-SCANNER-001"
DEMO_TIMEFRAMES = ["5m", "30m", "1h", "4h", "1d"]
DEMO_BARS_COUNT = 35   # enough for all indicators (ATR-14, range-20, RVOL-21)


def build_demo_bars(symbols: list[str], cutoff_at: datetime) -> dict:
    """Build synthetic bars for all symbols across all timeframes."""
    bars: dict[str, dict] = {}
    for symbol in symbols:
        bars[symbol] = {}
        for tf in DEMO_TIMEFRAMES:
            bars[symbol][tf] = make_synthetic_bars(
                symbol=symbol,
                timeframe=tf,
                cutoff_at=cutoff_at,
                count=DEMO_BARS_COUNT,
            )
    return bars


def run_demo() -> dict:
    """Execute a full offline demo scan and return a summary dict."""

    # 1. Build universe
    universe = make_synthetic_universe(
        symbols=DEMO_SYMBOLS,
        cutoff_at=DEMO_CUTOFF,
        ineligible_symbols=DEMO_INELIGIBLE,
    )

    # 2. Build bars
    eligible_symbols = [x.symbol for x in universe.eligible]
    bars = build_demo_bars(eligible_symbols, DEMO_CUTOFF)

    # 3. Source manifest
    dataset_payload = {"symbols": DEMO_SYMBOLS, "cutoff_at": DEMO_CUTOFF.isoformat()}
    dataset_sha = sha256_hex(canonical_bytes(dataset_payload))
    manifest = SourceManifest(
        dataset_id="AQL-DEMO-DATASET-V1",
        dataset_sha=dataset_sha,
        schema_version="AQL-SCANNER-V1",
        cutoff_at=DEMO_CUTOFF,
        created_at=DEMO_CUTOFF,
    )

    # 4. Run config
    config = ScanRunConfig(
        scanner_id=DEMO_SCANNER_ID,
        candidate_limit=10,
        candidate_offset=0,
    )

    # 5. Execute scan
    engine = OfflineScannerEngine(config, manifest)
    run = engine.scan(
        universe=universe,
        bars_by_symbol_tf=bars,
        cutoff_at=DEMO_CUTOFF,
        include_all_envelopes=True,
    )

    # 6. Summarise results
    summary = run.summary()
    summary["nominated"] = []
    for env in run.nominated_envelopes:
        summary["nominated"].append({
            "symbol": env.candidate_id.split(":")[0],
            "profile": env.profile_id,
            "stage": env.stage,
            "score": env.score,
            "digest": env.digest,
        })
    summary["all_envelopes_digest_sample"] = [
        {"symbol": env.candidate_id.split(":")[0], "profile": env.profile_id,
         "stage": env.stage, "digest": env.digest[:12] + "..."}
        for env in run.envelopes[:5]
    ]
    summary["errors"] = run.errors
    summary["publishable_check"] = all(not e.publishable for e in run.envelopes)
    summary["delivery_authorized_check"] = all(not e.delivery_authorized for e in run.envelopes)

    return summary


if __name__ == "__main__":
    result = run_demo()
    print(json.dumps(result, indent=2, default=str))
