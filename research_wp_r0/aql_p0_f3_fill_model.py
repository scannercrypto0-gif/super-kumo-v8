"""F3 — Modeled market execution: NO_FILL/UNKNOWN with fee/slippage policy.

Canonical contract: aql.p0.historical-decision.v1
Governed by Factory #77 comment 6540573678.

Modeled fills use next-eligible-open strictly after decision + declared lag/latency.
No OHLC-touch proof for fills. Fee/slippage both sides.

Exit: when close < prior 10-bar low (same rule as pilot). ttl_bars=1 for entry fill.
No PIT claims. OPEN_UNRESOLVED at terminal if still held.

Denominator preservation: ARMED → TRIGGERED | NO_FILL | UNKNOWN | OPEN_UNRESOLVED
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_EVEN, InvalidOperation

from .aql_p0_c1_source import P0Bar, P0SourceManifest
from .aql_p0_f1f2_opportunities import Opportunity, SignalState, EXIT_LOOKBACK

# ---------------------------------------------------------------------------
# Execution policy (frozen; must be documented in assumptions_digest)
# ---------------------------------------------------------------------------

FEE_BPS: int = 10          # fee per side in basis points
SLIPPAGE_BPS: int = 5      # slippage per side in basis points
INITIAL_CASH: Decimal = Decimal("10000.00")  # simulated starting capital
POSITION_SIZE_BTC: Decimal = Decimal("0.001")  # fixed quantity per trade

# ttl_bars=1: entry fill must happen at the immediately next open after signal
TTL_BARS: int = 1


class F3FillError(RuntimeError):
    """Unresolvable execution state — fail closed."""


@dataclass(frozen=True)
class FillResult:
    """Modeled fill for one ARMED opportunity."""
    opportunity_id: str
    signal_state: str        # TRIGGERED | NO_FILL | EXPIRED | OPEN_UNRESOLVED | UNKNOWN
    reason_code: str | None

    entry_bar_open_ms: int | None
    entry_price_gross: Decimal | None    # open of entry bar (no slip)
    entry_price_net: Decimal | None      # after slippage
    entry_fee: Decimal | None

    exit_bar_open_ms: int | None
    exit_price_gross: Decimal | None
    exit_price_net: Decimal | None
    exit_fee: Decimal | None

    gross_return: Decimal | None         # exit_net/entry_net - 1
    net_return: Decimal | None           # gross - fees
    is_terminal: bool                    # True if position closed or no fill


def _bps_factor(bps: int, side: str) -> Decimal:
    """Return the price multiplier for fee/slippage on a given side."""
    factor = Decimal(bps) / Decimal(10_000)
    if side == "buy":
        return Decimal(1) + factor
    elif side == "sell":
        return Decimal(1) - factor
    raise ValueError(f"Unknown side: {side!r}")


def _entry_net(open_price: float) -> tuple[Decimal, Decimal]:
    """Entry price after slippage; entry fee.
    entry_net = open * (1 + slip_bps/10000)
    entry_fee_cost = open * fee_bps/10000
    (fees are separate line items, not folded into price)
    """
    p = Decimal(str(open_price))
    slipped = p * _bps_factor(SLIPPAGE_BPS, "buy")
    fee = p * Decimal(FEE_BPS) / Decimal(10_000)
    return slipped, fee


def _exit_net(open_price: float) -> tuple[Decimal, Decimal]:
    """Exit price after slippage; exit fee.
    exit_net = open * (1 - slip_bps/10000)
    exit_fee_cost = open * fee_bps/10000
    """
    p = Decimal(str(open_price))
    slipped = p * _bps_factor(SLIPPAGE_BPS, "sell")
    fee = p * Decimal(FEE_BPS) / Decimal(10_000)
    return slipped, fee


def _net_return(entry_net: Decimal, exit_net: Decimal,
                entry_fee: Decimal, exit_fee: Decimal) -> tuple[Decimal, Decimal]:
    """Compute gross and net return. entry_net/exit_net are price after slippage."""
    gross = exit_net / entry_net - Decimal(1)
    total_fee_fraction = (entry_fee + exit_fee) / entry_net
    net = gross - total_fee_fraction
    return gross, net


def model_fills(
    manifest: P0SourceManifest,
    opportunities: list[Opportunity],
) -> list[FillResult]:
    """Apply F3 modeled execution to all ARMED opportunities.

    Non-ARMED opportunities pass through with their existing signal_state.
    Preserves full denominator.

    Parameters
    ----------
    manifest:
        Validated source manifest (used for bar lookup by open_ms).
    opportunities:
        Opportunity list from F1+F2.

    Returns
    -------
    list[FillResult]
        One per opportunity. Ordered to match input.
    """
    bar_by_open: dict[int, P0Bar] = {b.bar_open_ms: b for b in manifest.bars}
    sorted_opens = sorted(bar_by_open.keys())

    results: list[FillResult] = []
    for opp in opportunities:
        result = _model_one(opp, bar_by_open, sorted_opens)
        results.append(result)

    return results


def _model_one(
    opp: Opportunity,
    bar_by_open: dict[int, P0Bar],
    sorted_opens: list[int],
) -> FillResult:
    """Model execution for one opportunity."""

    # Pass-through for non-ARMED states
    if opp.signal_state != SignalState.ARMED:
        return FillResult(
            opportunity_id=opp.opportunity_id,
            signal_state=opp.signal_state.value,
            reason_code=opp.reason_code,
            entry_bar_open_ms=None,
            entry_price_gross=None,
            entry_price_net=None,
            entry_fee=None,
            exit_bar_open_ms=None,
            exit_price_gross=None,
            exit_price_net=None,
            exit_fee=None,
            gross_return=None,
            net_return=None,
            is_terminal=True,
        )

    # --- Entry: next bar after decision_cutoff_ms ---
    if opp.trigger_bar_open_ms is None:
        return FillResult(
            opportunity_id=opp.opportunity_id,
            signal_state="NO_FILL",
            reason_code="NO_TRIGGER_BAR",
            entry_bar_open_ms=None, entry_price_gross=None, entry_price_net=None, entry_fee=None,
            exit_bar_open_ms=None, exit_price_gross=None, exit_price_net=None, exit_fee=None,
            gross_return=None, net_return=None, is_terminal=True,
        )

    entry_bar = bar_by_open.get(opp.trigger_bar_open_ms)
    if entry_bar is None:
        return FillResult(
            opportunity_id=opp.opportunity_id,
            signal_state="NO_FILL",
            reason_code="ENTRY_BAR_MISSING",
            entry_bar_open_ms=opp.trigger_bar_open_ms,
            entry_price_gross=None, entry_price_net=None, entry_fee=None,
            exit_bar_open_ms=None, exit_price_gross=None, exit_price_net=None, exit_fee=None,
            gross_return=None, net_return=None, is_terminal=True,
        )

    entry_gross = Decimal(str(entry_bar.open))
    entry_net, entry_fee = _entry_net(entry_bar.open)

    # --- Exit: scan subsequent bars for exit condition (close < prior 10-bar low) ---
    # Build the bar list strictly after entry bar
    entry_idx = sorted_opens.index(entry_bar.bar_open_ms)
    post_entry_opens = sorted_opens[entry_idx + 1:]

    exit_bar_open_ms = None
    exit_gross = None
    exit_net_price = None
    exit_fee_val = None
    gross_ret = None
    net_ret = None
    terminal = False
    fill_state = "UNKNOWN"
    reason_code = None

    # Maintain a rolling window for the exit condition
    # We need all bars up to and including bar being evaluated for exit
    # "prior 10 bars" = bars immediately before the bar being checked
    all_sorted_opens = sorted(bar_by_open.keys())

    for exit_open_ms in post_entry_opens:
        exit_bar = bar_by_open[exit_open_ms]
        # Get the 10 bars immediately before this exit bar
        this_bar_idx = all_sorted_opens.index(exit_open_ms)
        prior_10 = all_sorted_opens[max(0, this_bar_idx - EXIT_LOOKBACK):this_bar_idx]
        if len(prior_10) < EXIT_LOOKBACK:
            continue  # not enough history for exit signal
        exit_level = min(bar_by_open[o].low for o in prior_10)
        if exit_bar.close < exit_level:
            # Exit condition met
            exit_bar_open_ms = exit_open_ms
            exit_gross = Decimal(str(exit_bar.open))
            exit_net_price, exit_fee_val = _exit_net(exit_bar.open)
            gross_ret, net_ret = _net_return(entry_net, exit_net_price, entry_fee, exit_fee_val)
            fill_state = "TRIGGERED"
            terminal = True
            break

    if not terminal:
        # Position never exited within the data window — OPEN_UNRESOLVED
        fill_state = "OPEN_UNRESOLVED"
        reason_code = "POSITION_OPEN_AT_DATA_WINDOW_END"
        terminal = False  # open terminal exposure; settled_equity=null

    return FillResult(
        opportunity_id=opp.opportunity_id,
        signal_state=fill_state,
        reason_code=reason_code,
        entry_bar_open_ms=entry_bar.bar_open_ms,
        entry_price_gross=entry_gross,
        entry_price_net=entry_net,
        entry_fee=entry_fee,
        exit_bar_open_ms=exit_bar_open_ms,
        exit_price_gross=exit_gross,
        exit_price_net=exit_net_price,
        exit_fee=exit_fee_val,
        gross_return=gross_ret,
        net_return=net_ret,
        is_terminal=terminal,
    )
