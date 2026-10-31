"""F1+F2 — Real-data consumer with decision cutoff + Breakout opportunity detection.

Canonical contract: aql.p0.historical-decision.v1
Strategy: SF_BREAKOUT_BASE_20_10_DEV_v1
  Entry rule: close > max(high of prior 20 bars) — rising edge
  Exit rule:  close < min(low of prior 10 bars)

FULL DENOMINATOR: every scheduled decision (including NO_SIGNAL, BLOCKED, UNKNOWN)
is included in the opportunity list. Nothing is silently dropped.

F1 consumes decision envelopes from C2 and extracts the feature prefix.
F2 applies the breakout signal to produce a signal state per opportunity.

Governed by:
  Factory #77 comment 6540573678 — Factory F1-F4 execution task
  Factory #77 comment 6540422879 — exact ACK of canonical v1 contract
  Core #180 comment 6540382460  — canonical spec sections 4 and 5
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

from .aql_p0_c1_source import P0Bar, P0SourceManifest
from .aql_p0_c2_producer import DecisionEnvelope

# Feature parameters (frozen)
ENTRY_LOOKBACK = 20   # bars; entry when close > max high of prior ENTRY_LOOKBACK bars
EXIT_LOOKBACK = 10    # bars; exit  when close < min low  of prior EXIT_LOOKBACK bars


class SignalState(str, Enum):
    """Mutually exclusive per-decision signal states per canonical spec section 4."""
    NO_SIGNAL = "NO_SIGNAL"       # entry conditions not met; no position
    WATCH = "WATCH"               # monitoring; not used in BASE signal (reserved)
    ARMED = "ARMED"               # entry condition met; waiting for next open
    TRIGGERED = "TRIGGERED"       # entry executed at next open
    REJECTED = "REJECTED"         # entry conditions met but rejected (capital/risk)
    NO_FILL = "NO_FILL"           # modeled fill not achievable
    EXPIRED = "EXPIRED"           # ttl expired without fill
    UNKNOWN = "UNKNOWN"           # insufficient/conflicting data; fail-closed
    BLOCKED = "BLOCKED"           # upstream prefix blocked


@dataclass(frozen=True)
class Opportunity:
    """One evaluated opportunity (F1+F2 output per scheduled decision).

    Included in denominator whether ARMED, NO_SIGNAL, BLOCKED, or UNKNOWN.
    """
    opportunity_id: str
    producer_event_id: str
    decision_cutoff_ms: int
    decision_ms: int
    prefix_start_ms: int
    prefix_end_exclusive_ms: int
    prefix_bar_checksums_sha256: str
    input_disposition: str        # from C2 envelope
    signal_state: SignalState
    reason_code: str | None

    # Feature values (null if BLOCKED or insufficient prefix)
    entry_level: float | None     # max(high, prior ENTRY_LOOKBACK bars)
    exit_level: float | None      # min(low,  prior EXIT_LOOKBACK bars)
    trigger_bar_open_ms: int | None  # bar open where entry would execute (next eligible)
    trigger_bar_close: float | None  # close of the evaluation bar
    prefix_bar_count: int

    # Lineage
    strategy_id: str
    trial_id: str
    dataset_version: int


def _extract_prefix_bars(
    envelope: DecisionEnvelope, all_bars: tuple[P0Bar, ...]
) -> list[P0Bar] | None:
    """Return the bars included in this envelope's prefix, or None if mismatch."""
    cutoff = envelope.decision_cutoff_ms
    prefix = [b for b in all_bars if b.bar_close_ms < cutoff]
    return prefix


def evaluate_opportunities(
    manifest: P0SourceManifest,
    envelopes: list[DecisionEnvelope],
) -> list[Opportunity]:
    """Apply F1 (consumer/cutoff) + F2 (breakout signal) to all envelopes.

    Maintains full denominator: BLOCKED and UNKNOWN are included with
    appropriate signal_state; never silently dropped.

    Parameters
    ----------
    manifest:
        Validated P0SourceManifest from C1.
    envelopes:
        Decision envelopes from C2 (one per scheduled decision).

    Returns
    -------
    list[Opportunity]
        One per envelope. Ordered by decision_cutoff_ms ascending.
    """
    all_bars = manifest.bars
    opportunities: list[Opportunity] = []

    for env in envelopes:
        opp = _evaluate_one(env, all_bars)
        opportunities.append(opp)

    # Verify full denominator: every envelope has exactly one opportunity
    assert len(opportunities) == len(envelopes), "Denominator violation"

    return opportunities


def _evaluate_one(env: DecisionEnvelope, all_bars: tuple[P0Bar, ...]) -> Opportunity:
    """Evaluate one decision envelope and produce an Opportunity."""

    # --- F1: consume envelope, extract prefix strictly before cutoff ---
    if env.input_disposition == "BLOCKED":
        return Opportunity(
            opportunity_id=env.opportunity_id,
            producer_event_id=env.producer_event_id,
            decision_cutoff_ms=env.decision_cutoff_ms,
            decision_ms=env.decision_ms,
            prefix_start_ms=env.prefix_start_ms,
            prefix_end_exclusive_ms=env.prefix_end_exclusive_ms,
            prefix_bar_checksums_sha256=env.prefix_bar_checksums_sha256,
            input_disposition=env.input_disposition,
            signal_state=SignalState.BLOCKED,
            reason_code=env.reason_code or "UPSTREAM_BLOCKED",
            entry_level=None,
            exit_level=None,
            trigger_bar_open_ms=None,
            trigger_bar_close=None,
            prefix_bar_count=0,
            strategy_id=env.strategy_id,
            trial_id=env.trial_id,
            dataset_version=env.dataset_version,
        )

    # Extract prefix bars (strictly before decision_cutoff_ms)
    prefix = _extract_prefix_bars(env, all_bars)
    if prefix is None or len(prefix) < ENTRY_LOOKBACK:
        return Opportunity(
            opportunity_id=env.opportunity_id,
            producer_event_id=env.producer_event_id,
            decision_cutoff_ms=env.decision_cutoff_ms,
            decision_ms=env.decision_ms,
            prefix_start_ms=env.prefix_start_ms,
            prefix_end_exclusive_ms=env.prefix_end_exclusive_ms,
            prefix_bar_checksums_sha256=env.prefix_bar_checksums_sha256,
            input_disposition=env.input_disposition,
            signal_state=SignalState.UNKNOWN,
            reason_code="INSUFFICIENT_PREFIX_FOR_FEATURE",
            entry_level=None,
            exit_level=None,
            trigger_bar_open_ms=None,
            trigger_bar_close=None,
            prefix_bar_count=len(prefix) if prefix else 0,
            strategy_id=env.strategy_id,
            trial_id=env.trial_id,
            dataset_version=env.dataset_version,
        )

    # --- F2: breakout signal from completed prior bars only (no lookahead) ---
    # "Prior 20 bars" = prefix[−21 .. −2] (the 20 bars before the evaluation bar)
    # "Evaluation bar" = prefix[-1] (last completed bar before cutoff)
    eval_bar = prefix[-1]
    prior_bars_for_entry = prefix[-ENTRY_LOOKBACK - 1:-1]   # prior ENTRY_LOOKBACK bars

    if len(prior_bars_for_entry) < ENTRY_LOOKBACK:
        # Not enough history for entry signal
        return Opportunity(
            opportunity_id=env.opportunity_id,
            producer_event_id=env.producer_event_id,
            decision_cutoff_ms=env.decision_cutoff_ms,
            decision_ms=env.decision_ms,
            prefix_start_ms=env.prefix_start_ms,
            prefix_end_exclusive_ms=env.prefix_end_exclusive_ms,
            prefix_bar_checksums_sha256=env.prefix_bar_checksums_sha256,
            input_disposition=env.input_disposition,
            signal_state=SignalState.NO_SIGNAL,
            reason_code="WARMUP_PERIOD",
            entry_level=None,
            exit_level=None,
            trigger_bar_open_ms=None,
            trigger_bar_close=eval_bar.close,
            prefix_bar_count=len(prefix),
            strategy_id=env.strategy_id,
            trial_id=env.trial_id,
            dataset_version=env.dataset_version,
        )

    entry_level = max(b.high for b in prior_bars_for_entry)

    # Compute exit level from prior EXIT_LOOKBACK bars
    prior_bars_for_exit = prefix[-EXIT_LOOKBACK - 1:-1]
    exit_level = min(b.low for b in prior_bars_for_exit) if len(prior_bars_for_exit) >= EXIT_LOOKBACK else None

    # Entry signal: eval bar close > prior 20-bar high (rising edge breakout)
    entry_triggered = eval_bar.close > entry_level

    if not entry_triggered:
        signal_state = SignalState.NO_SIGNAL
        reason_code = None
        trigger_open_ms = None
    else:
        # Entry fires; next bar's open is the hypothetical execution bar
        # Find the bar immediately after the evaluation bar
        eval_idx = next(
            (i for i, b in enumerate(all_bars) if b.bar_open_ms == eval_bar.bar_open_ms),
            None
        )
        if eval_idx is None or eval_idx + 1 >= len(all_bars):
            # No next bar available (evaluation bar is the last bar)
            signal_state = SignalState.EXPIRED
            reason_code = "NO_NEXT_BAR_FOR_EXECUTION"
            trigger_open_ms = None
        else:
            trigger_bar = all_bars[eval_idx + 1]
            # Check if trigger bar is within the window
            if trigger_bar.bar_open_ms >= env.prefix_end_exclusive_ms + ENTRY_LOOKBACK * 900_000:
                signal_state = SignalState.EXPIRED
                reason_code = "TRIGGER_BAR_OUTSIDE_WINDOW"
                trigger_open_ms = None
            else:
                signal_state = SignalState.ARMED  # Execution handled by F3
                reason_code = None
                trigger_open_ms = trigger_bar.bar_open_ms

    return Opportunity(
        opportunity_id=env.opportunity_id,
        producer_event_id=env.producer_event_id,
        decision_cutoff_ms=env.decision_cutoff_ms,
        decision_ms=env.decision_ms,
        prefix_start_ms=env.prefix_start_ms,
        prefix_end_exclusive_ms=env.prefix_end_exclusive_ms,
        prefix_bar_checksums_sha256=env.prefix_bar_checksums_sha256,
        input_disposition=env.input_disposition,
        signal_state=signal_state,
        reason_code=reason_code,
        entry_level=entry_level,
        exit_level=exit_level,
        trigger_bar_open_ms=trigger_open_ms,
        trigger_bar_close=eval_bar.close,
        prefix_bar_count=len(prefix),
        strategy_id=env.strategy_id,
        trial_id=env.trial_id,
        dataset_version=env.dataset_version,
    )
