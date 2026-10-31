"""F3 — Modeled market execution: NO_FILL/UNKNOWN with fee/slippage policy.

Canonical contract: aql.p0.historical-decision.v1
Governed by Factory #77 comment 6540573678.
PM Consolidated Correction Order PR #204 comment 6540907647.

Modeled fills use next-eligible-open strictly after decision + declared lag/latency.
No OHLC-touch proof for fills. Fee/slippage both sides.

Exit: close < prior 10-bar low triggers exit signal at close.
EXECUTION is at the NEXT bar's open — NOT the same bar whose close confirmed
the signal (temporal causality: close is known only after the bar ends).

TTL_BARS=1 for entry fill: entry must happen at the immediately next open after signal.
Single-position exposure enforcement: REJECTED if already in position when ARMED.
Cash sufficiency enforcement: REJECTED if insufficient cash for entry cost.
OPEN_UNRESOLVED at terminal if position not exited within data window.

Denominator preservation: ARMED → TRIGGERED | NO_FILL | EXPIRED | UNKNOWN |
                                   OPEN_UNRESOLVED | REJECTED
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
    signal_state: str        # TRIGGERED | NO_FILL | EXPIRED | OPEN_UNRESOLVED | UNKNOWN | REJECTED
    reason_code: str | None

    entry_bar_open_ms: int | None
    entry_price_gross: Decimal | None    # open of entry bar (no slip)
    entry_price_net: Decimal | None      # after slippage
    entry_fee: Decimal | None

    exit_bar_open_ms: int | None         # the EXECUTION bar (bar AFTER the signal bar)
    exit_price_gross: Decimal | None     # open of execution bar (no slip)
    exit_price_net: Decimal | None       # after slippage
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
    """Entry price after slippage; entry fee per BTC.
    entry_net = open * (1 + slip_bps/10000)
    entry_fee  = open * fee_bps/10000    [per BTC, separate line item]
    """
    p = Decimal(str(open_price))
    slipped = p * _bps_factor(SLIPPAGE_BPS, "buy")
    fee = p * Decimal(FEE_BPS) / Decimal(10_000)
    return slipped, fee


def _exit_net(open_price: float) -> tuple[Decimal, Decimal]:
    """Exit price after slippage; exit fee per BTC.
    exit_net  = open * (1 - slip_bps/10000)
    exit_fee   = open * fee_bps/10000    [per BTC, separate line item]
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

    Single-position exposure and cash sufficiency are enforced chronologically:
    a new ARMED signal while a position is already held → REJECTED.

    Parameters
    ----------
    manifest:
        Validated source manifest (used for bar lookup by open_ms).
    opportunities:
        Opportunity list from F1+F2, in chronological order.

    Returns
    -------
    list[FillResult]
        One per opportunity. Ordered to match input.
    """
    bar_by_open: dict[int, P0Bar] = {b.bar_open_ms: b for b in manifest.bars}
    sorted_opens = sorted(bar_by_open.keys())

    results: list[FillResult] = []
    held_position: bool = False
    simulated_cash: Decimal = INITIAL_CASH

    for opp in opportunities:
        result, held_position, simulated_cash = _model_one(
            opp, bar_by_open, sorted_opens, held_position, simulated_cash
        )
        results.append(result)

    return results


def _model_one(
    opp: Opportunity,
    bar_by_open: dict[int, P0Bar],
    sorted_opens: list[int],
    held_position: bool,
    simulated_cash: Decimal,
) -> tuple[FillResult, bool, Decimal]:
    """Model execution for one opportunity.

    Returns (FillResult, new_held_position, new_simulated_cash).
    """

    def _no_fill(state: str, reason: str, is_terminal: bool = True) -> FillResult:
        return FillResult(
            opportunity_id=opp.opportunity_id,
            signal_state=state,
            reason_code=reason,
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
            is_terminal=is_terminal,
        )

    # Pass-through for non-ARMED states
    if opp.signal_state != SignalState.ARMED:
        return (
            FillResult(
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
            ),
            held_position,
            simulated_cash,
        )

    # --- Single-position exposure enforcement ---
    # Rising-edge semantics: if we're already holding a position, reject the new ARMED signal.
    if held_position:
        return (
            _no_fill("REJECTED", "POSITION_ALREADY_OPEN"),
            held_position,
            simulated_cash,
        )

    # --- Entry: next bar after decision_cutoff_ms ---
    if opp.trigger_bar_open_ms is None:
        return (_no_fill("NO_FILL", "NO_TRIGGER_BAR"), held_position, simulated_cash)

    entry_bar = bar_by_open.get(opp.trigger_bar_open_ms)
    if entry_bar is None:
        return (_no_fill("NO_FILL", "ENTRY_BAR_MISSING"), held_position, simulated_cash)

    entry_gross = Decimal(str(entry_bar.open))
    entry_net, entry_fee = _entry_net(entry_bar.open)

    # --- Cash sufficiency check ---
    # Total cash outlay = (net_price + fee) * position_size
    entry_cost = (entry_net + entry_fee) * POSITION_SIZE_BTC
    if simulated_cash < entry_cost:
        return (
            _no_fill("REJECTED", "INSUFFICIENT_CASH"),
            held_position,
            simulated_cash,
        )

    # --- Entry fill committed ---
    new_cash = simulated_cash - entry_cost
    new_held = True

    # --- Exit scan: close < prior 10-bar low (signal bar) → execute at NEXT bar's open ---
    # TEMPORAL CAUSALITY:
    #   Signal bar close confirms the exit condition (only known after bar ends).
    #   Execution MUST use the NEXT bar's open — we CANNOT execute at the same bar's
    #   open because the close is only observable after the open.
    entry_idx = sorted_opens.index(entry_bar.bar_open_ms)
    post_entry_opens = sorted_opens[entry_idx + 1:]
    all_sorted_opens = sorted_opens  # alias for clarity

    exit_bar_open_ms = None
    exit_gross = None
    exit_net_price = None
    exit_fee_val = None
    gross_ret = None
    net_ret = None
    fill_state = "UNKNOWN"
    reason_code: str | None = None
    terminal = False

    for signal_open_ms in post_entry_opens:
        signal_bar = bar_by_open[signal_open_ms]
        this_bar_idx = all_sorted_opens.index(signal_open_ms)

        # Prior 10 bars = bars immediately before signal_bar (not including it)
        prior_10_opens = all_sorted_opens[max(0, this_bar_idx - EXIT_LOOKBACK):this_bar_idx]
        if len(prior_10_opens) < EXIT_LOOKBACK:
            continue  # not enough history for exit signal

        exit_level = min(bar_by_open[o].low for o in prior_10_opens)

        if signal_bar.close < exit_level:
            # EXIT SIGNAL confirmed at signal_bar.close
            # EXECUTION at the NEXT bar's open (temporal causality fix)
            exec_idx = this_bar_idx + 1
            if exec_idx >= len(all_sorted_opens):
                # No next bar available — position cannot be exited
                # Fall through to OPEN_UNRESOLVED below
                break
            exec_open_ms = all_sorted_opens[exec_idx]
            exec_bar = bar_by_open[exec_open_ms]

            exit_bar_open_ms = exec_open_ms
            exit_gross = Decimal(str(exec_bar.open))
            exit_net_price, exit_fee_val = _exit_net(exec_bar.open)
            gross_ret, net_ret = _net_return(entry_net, exit_net_price, entry_fee, exit_fee_val)
            fill_state = "TRIGGERED"
            terminal = True

            # Update cash: receive (exit_net - exit_fee) * qty
            exit_proceeds = (exit_net_price - exit_fee_val) * POSITION_SIZE_BTC
            new_cash = new_cash + exit_proceeds
            new_held = False
            break

    if not terminal:
        # Position never exited within the data window — OPEN_UNRESOLVED
        # new_held remains True; position is still open at window end
        fill_state = "OPEN_UNRESOLVED"
        reason_code = "POSITION_OPEN_AT_DATA_WINDOW_END"
        terminal = False

    result = FillResult(
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
    return result, new_held, new_cash
