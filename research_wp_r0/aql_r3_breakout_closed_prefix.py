"""R3 read-only Breakout 20/10 evaluation for a supplied CLOSED prefix.

This is the existing P0 historical decision rule, extracted for one decision
without looking up a future bar. No G2 runtime is connected or manufactured.
RETROSPECTIVE_NON_PIT input stays research-only and UNVERIFIED.
"""
from __future__ import annotations

from typing import Any, Mapping, Sequence
from decimal import Decimal

from .aql_f1_decision_capture_v1 import CaptureError, digest
from .aql_p0_f1f2_opportunities import ENTRY_LOOKBACK, EXIT_LOOKBACK


def evaluate_breakout_closed_prefix(
    bars: Sequence[Sequence[Any]], *,
    decision_cutoff_ms: int,
    availability_mode: str,
    source_id: str,
    source_version: str,
    correction_generation: str,
    strategy_id: str = "SF_BREAKOUT_BASE_20_10_DEV_v1",
    strategy_version: str = "1",
    expected_prefix_sha256: str | None = None,
) -> dict:
    """Pure nontrading decision from all and ONLY the supplied closed bars.

    Input rows: (open_ms, close_ms, open, high, low, close, volume).
    The caller is responsible for independent source-time proof; this
    evaluator cannot establish real publication/receipt time from OHLCV.
    """
    if availability_mode not in ("RETROSPECTIVE_NON_PIT", "PROSPECTIVE_CAPTURE"):
        raise CaptureError("R3_AVAILABILITY_MODE_INVALID")
    if type(decision_cutoff_ms) is not int or decision_cutoff_ms <= 0:
        raise CaptureError("R3_CUTOFF_INVALID")
    if any(type(x) is not str or not x for x in
           (source_id, source_version, correction_generation, strategy_id, strategy_version)):
        raise CaptureError("R3_SOURCE_OR_STRATEGY_IDENTITY_REQUIRED")
    if strategy_id != "SF_BREAKOUT_BASE_20_10_DEV_v1" or strategy_version != "1":
        raise CaptureError("R3_UNAPPROVED_STRATEGY_DRIFT")
    if not isinstance(bars, (list, tuple)):
        raise CaptureError("R3_PREFIX_REQUIRED")
    checked = []
    for row in bars:
        if not isinstance(row, (list, tuple)) or len(row) != 7:
            raise CaptureError("R3_BAR_SHAPE")
        opening, closing = row[:2]
        if (type(opening) is not int or type(closing) is not int
                or opening < 0 or opening % 900000
                or closing != opening + 899999
                or closing >= decision_cutoff_ms):
            raise CaptureError("R3_FUTURE_OR_NONFINAL_BAR")
        if checked and opening != checked[-1][0] + 900000:
            raise CaptureError("R3_GAP_DUPLICATE_OR_OUT_OF_ORDER")
        vals = row[2:]
        import math
        if (any(type(v) not in (int, float) or not math.isfinite(v) for v in vals)
                or min(vals[:4]) <= 0 or vals[4] < 0
                or vals[1] < max(vals[0], vals[2], vals[3])
                or vals[2] > min(vals[0], vals[3])):
            raise CaptureError("R3_BAD_OHLCV")
        checked.append(tuple(row))
    if not checked:
        raise CaptureError("R3_EMPTY_PREFIX")
    if checked[-1][1] + 1 != decision_cutoff_ms:
        raise CaptureError("R3_LAST_BAR_NOT_AT_CUTOFF")
    # Binds all input bars including OHLCV, never a digest claimed from a later bar.
    prefix_sha = digest([[r[0], r[1]] + [format(Decimal(str(v)).normalize(), 'f') for v in r[2:]] for r in checked])
    if expected_prefix_sha256 is not None and prefix_sha != expected_prefix_sha256:
        raise CaptureError("R3_PREFIX_SHA_DRIFT")
    eval_bar = checked[-1]
    prior = checked[-ENTRY_LOOKBACK-1:-1]
    if len(prior) < ENTRY_LOOKBACK:
        signal, reason, entry, exit_level = "NO_SIGNAL", "WARMUP_PERIOD", None, None
    else:
        entry = max(x[3] for x in prior)
        exit_prior = checked[-EXIT_LOOKBACK-1:-1]
        exit_level = min(x[4] for x in exit_prior)
        signal = "ARMED" if eval_bar[5] > entry else "NO_SIGNAL"
        reason = "AWAITING_F3_ELIGIBILITY_NOT_TRIGGERED" if signal == "ARMED" else None
    return {
        "schema_version": "aql.r3-breakout-closed-prefix-evaluation.v1",
        "strategy_id": strategy_id,
        "strategy_version": strategy_version,
        "source_id": source_id,
        "source_version": source_version,
        "correction_generation": correction_generation,
        "availability_mode": availability_mode,
        "proof_status": "BLOCKED_EXTERNAL_EVIDENCE",
        "original_g2_event_status": "NOT_CONNECTED",
        "decision_cutoff_ms": decision_cutoff_ms,
        "prefix_sha256": prefix_sha,
        "prefix_bar_count": len(checked),
        "feature_policy_version": "BASE-20-10-v1",
        "entry_level": str(entry) if entry is not None else None,
        "exit_level": str(exit_level) if exit_level is not None else None,
        "breakout_signal_state": signal,
        "reason_code": reason,
        "direction": None,
        "pre_f3_capture_status": "NOT_CONNECTED",
        "f3_monitor_status": "NOT_CONNECTED",
        "execution": "DISABLED",
    }
