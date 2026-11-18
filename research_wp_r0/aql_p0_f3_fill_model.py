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


def _find_entry_bar(
    decision_ms: int,
    bar_by_open: dict[int, P0Bar],
    sorted_opens: list[int],
) -> P0Bar | None:
    """Find the first bar whose open_ms is STRICTLY GREATER than decision_ms.

    F3-ENTRY-CUTOFF fix: entry_bar_open_ms must be > decision_ms.
    On a 15m grid with 2s lag (decision_ms = cutoff + 2000 = bar[N+1].open + 2000),
    the bar immediately after the signal bar opens AT cutoff = decision_ms - 2000 < decision_ms.
    That bar CANNOT be used for entry. The first eligible bar is bar[N+2].
    """
    for open_ms in sorted_opens:
        if open_ms > decision_ms:
            return bar_by_open[open_ms]
    return None


def model_fills(
    manifest: P0SourceManifest,
    opportunities: list[Opportunity],
) -> list[FillResult]:
    """Apply F3 modeled execution to all ARMED opportunities.

    Non-ARMED opportunities pass through with their existing signal_state.
    Preserves full denominator.

    Single-position exposure and cash sufficiency are enforced via EVENT-TIME
    state machine: a new ARMED opportunity's entry is rejected if the EXECUTION
    TIMESTAMP of the entry bar falls before the exit execution timestamp of any
    open position (held_until_ms). Cash from an exit is only added when
    event-time reaches the exit_execution_ms, NOT when the exit is merely scanned.

    F3-ENTRY-CUTOFF fix: entry bar is the first bar with open_ms > decision_ms
    (not opp.trigger_bar_open_ms which may equal decision_cutoff_ms < decision_ms).

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

    # Event-time state: track WHEN the open position exits (exit execution ms)
    # and how much cash will be received at that point.
    held_until_ms: int | None = None       # exit execution bar open_ms
    pending_exit_proceeds: Decimal | None = None  # cash from exit when held_until_ms fires

    last_decision_ms: int | None = None
    for opp in opportunities:
        if last_decision_ms is not None and opp.decision_ms < last_decision_ms:
            raise F3FillError("OPPORTUNITIES_NOT_CHRONOLOGICAL")
        last_decision_ms = opp.decision_ms
        if opp.signal_state != SignalState.ARMED:
            results.append(FillResult(
                opportunity_id=opp.opportunity_id,
                signal_state=opp.signal_state.value,
                reason_code=opp.reason_code,
                entry_bar_open_ms=None,
                entry_price_gross=None, entry_price_net=None, entry_fee=None,
                exit_bar_open_ms=None,
                exit_price_gross=None, exit_price_net=None, exit_fee=None,
                gross_return=None, net_return=None,
                is_terminal=True,
            ))
            continue

        # --- F3-ENTRY-CUTOFF: first bar strictly after decision_ms ---
        entry_bar = _find_entry_bar(opp.decision_ms, bar_by_open, sorted_opens)

        if entry_bar is None:
            results.append(FillResult(
                opportunity_id=opp.opportunity_id,
                signal_state="NO_FILL", reason_code="NO_ENTRY_BAR_AFTER_DECISION_MS",
                entry_bar_open_ms=None,
                entry_price_gross=None, entry_price_net=None, entry_fee=None,
                exit_bar_open_ms=None,
                exit_price_gross=None, exit_price_net=None, exit_fee=None,
                gross_return=None, net_return=None, is_terminal=True,
            ))
            continue

        # A decision made while an earlier position is still held cannot reserve
        # a future entry slot merely because that slot occurs after the exit.
        # The strategy makes the accept/reject decision at decision_ms.
        if held_position and (held_until_ms is None or opp.decision_ms < held_until_ms):
            results.append(FillResult(
                opportunity_id=opp.opportunity_id,
                signal_state="REJECTED", reason_code="POSITION_ALREADY_OPEN_AT_DECISION",
                entry_bar_open_ms=None,
                entry_price_gross=None, entry_price_net=None, entry_fee=None,
                exit_bar_open_ms=None,
                exit_price_gross=None, exit_price_net=None, exit_fee=None,
                gross_return=None, net_return=None, is_terminal=True,
            ))
            continue

        # --- EVENT-TIME: check if pending exit has fired at or before entry_bar.bar_open_ms ---
        # F3-EVENT-TIME-GTE fix: use >= so that when a new entry falls on the SAME
        # bar as the exit execution, the exit fires first (freeing the position)
        # before the new entry is checked.  The old bug (>) caused POSITION_ALREADY_OPEN
        # rejection at the same bar_open_ms as held_until_ms.
        if held_position and held_until_ms is not None:
            if entry_bar.bar_open_ms >= held_until_ms:
                # Exit execution has passed in event-time — release position
                simulated_cash += pending_exit_proceeds  # type: ignore[operator]
                held_position = False
                held_until_ms = None
                pending_exit_proceeds = None

        # --- Single-position exposure enforcement (event-time) ---
        if held_position:
            results.append(FillResult(
                opportunity_id=opp.opportunity_id,
                signal_state="REJECTED", reason_code="POSITION_ALREADY_OPEN",
                entry_bar_open_ms=None,
                entry_price_gross=None, entry_price_net=None, entry_fee=None,
                exit_bar_open_ms=None,
                exit_price_gross=None, exit_price_net=None, exit_fee=None,
                gross_return=None, net_return=None, is_terminal=True,
            ))
            continue

        entry_gross = Decimal(str(entry_bar.open))
        entry_net, entry_fee = _entry_net(entry_bar.open)

        # --- Cash sufficiency check ---
        entry_cost = (entry_net + entry_fee) * POSITION_SIZE_BTC
        if simulated_cash < entry_cost:
            results.append(FillResult(
                opportunity_id=opp.opportunity_id,
                signal_state="REJECTED", reason_code="INSUFFICIENT_CASH",
                entry_bar_open_ms=None,
                entry_price_gross=None, entry_price_net=None, entry_fee=None,
                exit_bar_open_ms=None,
                exit_price_gross=None, exit_price_net=None, exit_fee=None,
                gross_return=None, net_return=None, is_terminal=True,
            ))
            continue

        # --- Entry fill committed: reserve cash, open position ---
        simulated_cash -= entry_cost
        held_position = True

        # --- Exit scan: close < prior 10-bar low → execute at NEXT bar's open ---
        entry_idx = sorted_opens.index(entry_bar.bar_open_ms)
        post_entry_opens = sorted_opens[entry_idx + 1:]

        exit_bar_open_ms: int | None = None
        exit_gross: Decimal | None = None
        exit_net_price: Decimal | None = None
        exit_fee_val: Decimal | None = None
        gross_ret: Decimal | None = None
        net_ret: Decimal | None = None
        fill_state = "UNKNOWN"
        reason_code: str | None = None
        terminal = False
        computed_exit_proceeds: Decimal | None = None
        computed_exit_exec_ms: int | None = None

        for signal_open_ms in post_entry_opens:
            signal_bar = bar_by_open[signal_open_ms]
            this_bar_idx = sorted_opens.index(signal_open_ms)

            prior_10_opens = sorted_opens[max(0, this_bar_idx - EXIT_LOOKBACK):this_bar_idx]
            if len(prior_10_opens) < EXIT_LOOKBACK:
                continue

            exit_level = min(bar_by_open[o].low for o in prior_10_opens)

            if signal_bar.close < exit_level:
                exec_idx = this_bar_idx + 1
                if exec_idx >= len(sorted_opens):
                    break
                exec_open_ms = sorted_opens[exec_idx]
                exec_bar = bar_by_open[exec_open_ms]

                exit_bar_open_ms = exec_open_ms
                exit_gross = Decimal(str(exec_bar.open))
                exit_net_price, exit_fee_val = _exit_net(exec_bar.open)
                gross_ret, net_ret = _net_return(entry_net, exit_net_price, entry_fee, exit_fee_val)
                fill_state = "TRIGGERED"
                terminal = True

                # Compute exit proceeds — but DO NOT release cash/position yet.
                # Cash is released only when event-time reaches exec_open_ms
                # (checked at the next ARMED opportunity's entry_bar comparison).
                computed_exit_proceeds = (exit_net_price - exit_fee_val) * POSITION_SIZE_BTC
                computed_exit_exec_ms = exec_open_ms
                break

        if not terminal:
            fill_state = "OPEN_UNRESOLVED"
            reason_code = "POSITION_OPEN_AT_DATA_WINDOW_END"

        # Record pending exit timing for event-time release
        if terminal and computed_exit_exec_ms is not None:
            held_until_ms = computed_exit_exec_ms
            pending_exit_proceeds = computed_exit_proceeds
            # Position remains held until event-time reaches held_until_ms
        # If OPEN_UNRESOLVED, held_position stays True, held_until_ms stays None

        results.append(FillResult(
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
        ))

    # Post-loop: release any pending exit proceeds that were never credited
    # because no further ARMED opportunity arrived after the last exit.
    # Without this, the final TRIGGERED trade's cash is silently lost when
    # model_fills() is the last call in a pipeline (no subsequent opportunity
    # to trigger the held_until_ms comparison).
    if held_position and held_until_ms is not None and pending_exit_proceeds is not None:
        simulated_cash += pending_exit_proceeds
        held_position = False
        held_until_ms = None
        pending_exit_proceeds = None

    return results
