"""P2 first Breakout trial: preregistration and source-backed decisions, NO outcomes.

Input rows must be retained, independently authenticated Work #223 bar-index
records. This module NEVER fetches, scores outcomes, or opens the holdout.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from hashlib import sha256
import json

from .aql_p2_core_producer import (
    BAR_MS, EMBARGO_MIN_MS, ContractError, FrozenTrialV1,
    HistoricalSourceV1, HistoricalBarV1, P2HistoricalOpportunityV1,
    _hash, _require, schedule_pair, validate_bars,
)

FEB_START, FEB_END = 1706745600000, 1709251200000
AUG_START, AUG_END = 1722470400000, 1725148800000
HOLDOUT_START, HOLDOUT_END = 1761955200000, 1764547200000
LOOKBACK = 20
VOL_LIMIT = Decimal("0.03")
HORIZONS_MS = (4 * 3600000, 24 * 3600000, 72 * 3600000)
SOURCE_ARCHIVES = {
    "BINANCE-SPOT-BTCUSDT-15M-2024-02-DEV-v1":
        (FEB_START, FEB_END, "55066890cd3a76c97c05e94213311b17a4146d697f6abe8762b3edae8495b20e"),
    "BINANCE-SPOT-BTCUSDT-15M-2024-08-DEV-v1":
        (AUG_START, AUG_END, "44e084e916a4c661b2177741d71438916388c0d34554f63cb147973aac13b094"),
}


def canonical(obj):
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def frozen_prespec():
    """Fixed before any candidate outcome access; not a profitability claim."""
    return {
        "schema": "aql.p2.breakout-prereg.v1",
        "trial_id": "P2_BREAKOUT_20_VOL3_EXIT10_DEV_20261103_v1",
        "evidence_class": "RETROSPECTIVE_NON_PIT",
        "scope": "PERSONAL_NONCOMMERCIAL_NONPRODUCTION_RESEARCH_ONLY",
        "source_pins": {k: {"start_ms": v[0], "end_exclusive_ms": v[1],
                             "archive_sha256": v[2]} for k, v in SOURCE_ARCHIVES.items()},
        "development": "FEB2024", "validation": "AUG2024",
        "validation_not_unseen": True,
        "bar_interval_ms": BAR_MS,
        "indexing": "zero-based; at cutoff = close_ms+1 of signal bar i; features i-20..i-1 only; signal close[i] > max(high[i-20:i]); prior close = close[i-1]",
        "decision_grid": "one scheduled opportunity per i>=20, with i+1 existing; all dispositions retained",
        "direction": "LONG_MODELED_RESEARCH_POLICY_NOT_ORIGINAL_DIRECTION",
        "volatility": "(max(high[i-20:i])-min(low[i-20:i]))/close[i-1]",
        "shadow_exclude": "volatility > 0.03; equality accepted",
        "base": "close-confirmed LONG breakout over 20 preceding complete bars",
        "shadow": "BASE with exactly one volatility exclusion",
        "modeled_entry": "open[i+1] if present; no inferred actual fill",
        "modeled_exit": "open[i+11] (10 complete 15m bars after entry open), censored if missing",
        "fee_per_side": "0.001", "slippage_per_side": "0.0005",
        "cost_scope": "MODEL_ONLY_NO_ACTUAL_FILLS",
        "observation_horizons_ms": list(HORIZONS_MS),
        "horizon_scope": "separate research observation; NOT ten-bar modeled exit",
        "missingness": "fail closed on missing/nonfinal/invalid bars; UNKNOWN when required future entry/exit is unavailable; never fill from another month",
        "no_signal": "no close-confirmed breakout",
        "rejected": "SHADOW only: volatility > 0.03",
        "hypothesis": "SHADOW 3pct exclusion reduces adverse excursion vs BASE over same scheduled denominator; no posthoc threshold tuning",
        "primary_comparison": "all scheduled cutoffs, with NO_SIGNAL/REJECTED/UNKNOWN retained; Factory owns actual outcome metrics",
        "embargo_ms": EMBARGO_MIN_MS,
        "cohort_end_censor": "no modeled entry/exit or 4/24/72h label crosses monthly boundary; last 72h cannot have full 72h observation",
        "holdout_start_ms": HOLDOUT_START,
        "holdout_end_exclusive_ms": HOLDOUT_END,
        "holdout": "SEALED_NO_FETCH_NO_EVALUATION",
    }


def seal_protocol():
    spec = frozen_prespec()
    hypothesis = {"claim": spec["hypothesis"], "denominator": spec["primary_comparison"]}
    base = {"rule": spec["base"], "indexing": spec["indexing"], "entry": spec["modeled_entry"],
            "exit": spec["modeled_exit"], "fees": spec["fee_per_side"], "slippage": spec["slippage_per_side"]}
    shadow = {**base, "filter": spec["shadow_exclude"], "volatility": spec["volatility"]}
    hashes = {"hypothesis_sha256": _hash(hypothesis), "base_definition_sha256": _hash(base),
              "shadow_definition_sha256": _hash(shadow), "preregistration_sha256": _hash(spec)}
    trial = FrozenTrialV1.seal(trial_id=spec["trial_id"], **hashes,
        train_end_exclusive_ms=AUG_END, holdout_start_ms=HOLDOUT_START,
        holdout_end_exclusive_ms=HOLDOUT_END, embargo_ms=EMBARGO_MIN_MS)
    return spec, trial


def _decimal(value):
    try:
        x = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ContractError("INVALID_OHLC") from exc
    _require(x.is_finite() and x > 0, "INVALID_OHLC")
    return x


def produce_cohort(source: HistoricalSourceV1, bars, rows, trial: FrozenTrialV1):
    """Produce source-backed scheduled decisions, never outcomes or fills.

    Caller MUST authenticate private rows/index against retained Work manifest and
    bar-index digest BEFORE calling; matching row hashes alone is not authorization.
    """
    _require(source.source_id in SOURCE_ARCHIVES, "UNDECLARED_COHORT")
    start, end, archive_sha = SOURCE_ARCHIVES[source.source_id]
    _require(source.source_package_sha256 == archive_sha, "SOURCE_ARCHIVE_PIN_DRIFT")
    valid = validate_bars(source, bars)
    rows = tuple(rows)
    _require(len(rows) == len(valid) == (end-start)//BAR_MS, "COHORT_COVERAGE_MISMATCH")
    _require(valid[0].open_ms == start and valid[-1].close_ms + 1 == end,
             "COHORT_BOUNDARY_DRIFT")
    _require(trial.preregistration_sha256 == _hash(frozen_prespec()),
             "UNFROZEN_PREREGISTRATION")
    prices = []
    for b, row in zip(valid, rows):
        _require(row.get("dataset_id") == source.source_id
                 and row.get("open_ms") == b.open_ms
                 and row.get("close_ms") == b.close_ms
                 and row.get("bar_sha256") == b.content_sha256,
                 "UNVERIFIED_BAR_MAPPING")
        high, low, close = (_decimal(row.get(k)) for k in ("high", "low", "close"))
        _require(high >= low and low <= close <= high, "INVALID_OHLC_RANGE")
        prices.append((high, low, close))
    opportunities = []
    for i in range(LOOKBACK, len(valid)-1):
        prefix = valid[:i+1]
        cutoff = valid[i].close_ms + 1
        _require(all(b.available_at_ms is None or b.available_at_ms <= cutoff
                     for b in prefix), "KNOWN_AFTER_CUTOFF")
        previous = prices[i-LOOKBACK:i]
        highest = max(p[0] for p in previous)
        lowest = min(p[1] for p in previous)
        vol = (highest-lowest)/prices[i-1][2]
        breakout = prices[i][2] > highest
        disposition = "TRIGGERED" if breakout else "NO_SIGNAL"
        identity = _hash({"trial": trial.protocol_sha256, "source": source.source_id,
                          "cutoff": cutoff})
        # Explicitly modeled direction proof; NEVER claim an original P0 signal.
        direction = "LONG" if breakout else None
        evidence_ref = ("P2_MODELED_BREAKOUT:" + identity) if breakout else None
        prefix_sha = _hash({"source": source.source_package_sha256,
                            "bar_sha256": [b.content_sha256 for b in prefix]})
        opportunities.append(P2HistoricalOpportunityV1(
            trial_id=trial.trial_id, opportunity_id=identity,
            producer_event_id="P2_RESEARCH:" + identity,
            source_id=source.source_id, source_package_sha256=source.source_package_sha256,
            feature_prefix_sha256=prefix_sha, policy_sha256=trial.base_definition_sha256,
            decision_cutoff_ms=cutoff, decision_ms=cutoff,
            disposition=disposition, direction=direction,
            direction_evidence_ref=evidence_ref,
            regime=None, regime_source_sha256=None,
            reason_code=("BREAKOUT_SHADOW_EXCLUDED_VOL_GT_3PCT" if breakout and vol > VOL_LIMIT
                         else "BREAKOUT_BOTH_ARMS" if breakout else "NO_BREAKOUT")))
    return tuple(opportunities)


def build_development_schedule(source, bars, authenticated_rows, trial):
    """No private data read here; caller must supply authenticated retained rows."""
    opportunities = produce_cohort(source, bars, authenticated_rows, trial)
    return schedule_pair(trial, source, bars, opportunities, test_only=False)
