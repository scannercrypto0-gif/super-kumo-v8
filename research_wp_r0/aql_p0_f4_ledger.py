"""F4 — Independent financial ledger: idempotent replay/restart + immutable report.

Canonical contract: aql.p0.historical-decision.v1
Governed by Factory #77 comment 6540573678.

The F4 ledger is INDEPENDENT of the G1 operational store (DurablePositionJournal
and durable_journal.py are G1/runtime components; this ledger is research-only P0).

Invariants:
  - Full denominator: scheduled_decisions = sum of all final dispositions + pending
  - No profitability claims from incomplete or unresolvable positions
  - OPEN_UNRESOLVED contributes to open_exposure (not settled PnL)
  - Duplicate-key replay = NO-OP (idempotent)
  - Conflicting-payload replay = LEDGER_CONFLICT/STOP
  - Immutable once finalized: report hash covers all events
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from decimal import Decimal, ROUND_HALF_EVEN
from hashlib import sha256
from typing import Any

from .aql_p0_c1_source import _canonical_bytes, _sha256_hex
from .aql_p0_f1f2_opportunities import Opportunity, SignalState
from .aql_p0_f3_fill_model import FillResult, INITIAL_CASH, POSITION_SIZE_BTC


class LedgerConflictError(RuntimeError):
    """Same event_id previously applied with a different payload. STOP."""


# ---------------------------------------------------------------------------
# Ledger event types
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class LedgerEvent:
    """One immutable financial event."""
    event_id: str           # sha256(canonical({opportunity_id, kind, ...}))
    opportunity_id: str
    kind: str               # "ENTRY_DEBIT" | "EXIT_CREDIT" | "NO_ACTION"
    bar_open_ms: int | None
    price_net: Decimal | None
    quantity_btc: Decimal | None
    fee: Decimal | None
    cash_delta: Decimal | None    # positive = cash increase, negative = decrease
    cumulative_cash: Decimal | None
    held_btc_delta: Decimal | None
    cumulative_held_btc: Decimal | None


@dataclass
class LedgerState:
    """Mutable ledger state during replay."""
    cash: Decimal = field(default_factory=lambda: INITIAL_CASH)
    held_btc: Decimal = field(default_factory=lambda: Decimal("0"))
    events: list[LedgerEvent] = field(default_factory=list)
    applied_event_ids: dict[str, str] = field(default_factory=dict)  # id→payload_hash
    error: str | None = None


def _event_id(opportunity_id: str, kind: str, bar_open_ms: int | None) -> str:
    payload = {"bar_open_ms": bar_open_ms, "kind": kind, "opportunity_id": opportunity_id}
    return _sha256_hex(_canonical_bytes(payload))


def _event_payload_hash(event: LedgerEvent) -> str:
    payload = {
        "bar_open_ms": event.bar_open_ms,
        "cash_delta": str(event.cash_delta) if event.cash_delta is not None else None,
        "fee": str(event.fee) if event.fee is not None else None,
        "kind": event.kind,
        "opportunity_id": event.opportunity_id,
        "price_net": str(event.price_net) if event.price_net is not None else None,
        "quantity_btc": str(event.quantity_btc) if event.quantity_btc is not None else None,
    }
    return _sha256_hex(_canonical_bytes(payload))


def _apply_event(event: LedgerEvent, state: LedgerState) -> None:
    """Apply one event to ledger state. Idempotent: same id+payload = NO-OP."""
    ph = _event_payload_hash(event)
    if event.event_id in state.applied_event_ids:
        existing_ph = state.applied_event_ids[event.event_id]
        if existing_ph != ph:
            raise LedgerConflictError(
                f"LEDGER_CONFLICT: event_id={event.event_id!r} was previously applied "
                f"with payload_hash={existing_ph!r} but now has {ph!r}. STOP."
            )
        return  # idempotent NO-OP

    state.applied_event_ids[event.event_id] = ph

    if event.cash_delta is not None:
        state.cash += event.cash_delta
    if event.held_btc_delta is not None:
        state.held_btc += event.held_btc_delta

    state.events.append(event)


def build_ledger(
    opportunities: list[Opportunity],
    fill_results: list[FillResult],
    *,
    trial_id: str,
) -> tuple[LedgerState, "LedgerReport"]:
    """Apply all fill results to the ledger and produce an immutable report.

    Parameters
    ----------
    opportunities:
        F1+F2 output (for denominator tracking).
    fill_results:
        F3 output (one per opportunity).
    trial_id:
        Frozen trial identifier for report identity.

    Returns
    -------
    (LedgerState, LedgerReport)
    """
    assert len(opportunities) == len(fill_results), "Opportunity/fill count mismatch"

    state = LedgerState()

    # Denominator tracking
    counts: dict[str, int] = {
        "NO_SIGNAL": 0, "ARMED": 0, "TRIGGERED": 0, "NO_FILL": 0,
        "EXPIRED": 0, "UNKNOWN": 0, "BLOCKED": 0, "OPEN_UNRESOLVED": 0, "OTHER": 0,
    }
    open_exposure_btc = Decimal("0")

    for opp, fill in zip(opportunities, fill_results):
        # Count denominator
        state_key = fill.signal_state if fill.signal_state in counts else "OTHER"
        counts[state_key] += 1

        if fill.signal_state == "TRIGGERED" and fill.entry_price_net is not None:
            # Entry debit
            entry_cash_delta = -(fill.entry_price_net * POSITION_SIZE_BTC + fill.entry_fee * POSITION_SIZE_BTC)
            entry_event = LedgerEvent(
                event_id=_event_id(opp.opportunity_id, "ENTRY_DEBIT", fill.entry_bar_open_ms),
                opportunity_id=opp.opportunity_id,
                kind="ENTRY_DEBIT",
                bar_open_ms=fill.entry_bar_open_ms,
                price_net=fill.entry_price_net,
                quantity_btc=POSITION_SIZE_BTC,
                fee=fill.entry_fee * POSITION_SIZE_BTC,
                cash_delta=entry_cash_delta,
                cumulative_cash=None,  # set after apply
                held_btc_delta=POSITION_SIZE_BTC,
                cumulative_held_btc=None,
            )
            _apply_event(entry_event, state)

            if fill.exit_price_net is not None:
                # Exit credit
                exit_cash_delta = fill.exit_price_net * POSITION_SIZE_BTC - fill.exit_fee * POSITION_SIZE_BTC
                exit_event = LedgerEvent(
                    event_id=_event_id(opp.opportunity_id, "EXIT_CREDIT", fill.exit_bar_open_ms),
                    opportunity_id=opp.opportunity_id,
                    kind="EXIT_CREDIT",
                    bar_open_ms=fill.exit_bar_open_ms,
                    price_net=fill.exit_price_net,
                    quantity_btc=POSITION_SIZE_BTC,
                    fee=fill.exit_fee * POSITION_SIZE_BTC,
                    cash_delta=exit_cash_delta,
                    cumulative_cash=None,
                    held_btc_delta=-POSITION_SIZE_BTC,
                    cumulative_held_btc=None,
                )
                _apply_event(exit_event, state)

        elif fill.signal_state == "OPEN_UNRESOLVED":
            # Open position at window end: record entry, no exit credit
            if fill.entry_price_net is not None:
                entry_cash_delta = -(fill.entry_price_net * POSITION_SIZE_BTC + fill.entry_fee * POSITION_SIZE_BTC)
                entry_event = LedgerEvent(
                    event_id=_event_id(opp.opportunity_id, "ENTRY_DEBIT", fill.entry_bar_open_ms),
                    opportunity_id=opp.opportunity_id,
                    kind="ENTRY_DEBIT",
                    bar_open_ms=fill.entry_bar_open_ms,
                    price_net=fill.entry_price_net,
                    quantity_btc=POSITION_SIZE_BTC,
                    fee=fill.entry_fee * POSITION_SIZE_BTC,
                    cash_delta=entry_cash_delta,
                    cumulative_cash=None,
                    held_btc_delta=POSITION_SIZE_BTC,
                    cumulative_held_btc=None,
                )
                _apply_event(entry_event, state)
                open_exposure_btc += POSITION_SIZE_BTC
        else:
            # NO_SIGNAL, NO_FILL, BLOCKED, UNKNOWN, EXPIRED — no financial events
            pass

    # --- Produce immutable report ---
    total_scheduled = len(opportunities)
    sum_counts = sum(counts.values())
    assert sum_counts == total_scheduled, (
        f"Denominator invariant violated: {sum_counts} != {total_scheduled}"
    )

    # Closed trades PnL
    closed_net_returns: list[Decimal] = []
    for fill in fill_results:
        if fill.signal_state == "TRIGGERED" and fill.net_return is not None:
            closed_net_returns.append(fill.net_return)

    total_net_return = sum(closed_net_returns) if closed_net_returns else Decimal("0")
    avg_net_return = (total_net_return / len(closed_net_returns)
                      if closed_net_returns else None)

    report = LedgerReport(
        trial_id=trial_id,
        total_scheduled_decisions=total_scheduled,
        denominator_counts=dict(counts),
        closed_trades=len(closed_net_returns),
        open_unresolved=counts["OPEN_UNRESOLVED"],
        open_exposure_btc=open_exposure_btc,
        terminal_cash=state.cash,
        terminal_held_btc=state.held_btc,
        total_net_return_closed=total_net_return,
        average_net_return_closed=avg_net_return,
        settled_equity=state.cash if state.held_btc == Decimal("0") else None,
        event_count=len(state.events),
    )
    return state, report


@dataclass(frozen=True)
class LedgerReport:
    """Immutable final report. settled_equity=None if open positions remain."""
    trial_id: str
    total_scheduled_decisions: int
    denominator_counts: dict
    closed_trades: int
    open_unresolved: int
    open_exposure_btc: Decimal
    terminal_cash: Decimal
    terminal_held_btc: Decimal
    total_net_return_closed: Decimal
    average_net_return_closed: Decimal | None
    settled_equity: Decimal | None   # null if held_btc > 0
    event_count: int

    def report_sha256(self) -> str:
        """Immutable content hash of this report."""
        d = {
            "average_net_return_closed": str(self.average_net_return_closed) if self.average_net_return_closed is not None else None,
            "closed_trades": self.closed_trades,
            "denominator_counts": self.denominator_counts,
            "event_count": self.event_count,
            "open_exposure_btc": str(self.open_exposure_btc),
            "open_unresolved": self.open_unresolved,
            "settled_equity": str(self.settled_equity) if self.settled_equity is not None else None,
            "terminal_cash": str(self.terminal_cash),
            "terminal_held_btc": str(self.terminal_held_btc),
            "total_net_return_closed": str(self.total_net_return_closed),
            "total_scheduled_decisions": self.total_scheduled_decisions,
            "trial_id": self.trial_id,
        }
        return _sha256_hex(_canonical_bytes(d))

    def to_dict(self) -> dict:
        return {
            "average_net_return_closed": str(self.average_net_return_closed) if self.average_net_return_closed is not None else None,
            "closed_trades": self.closed_trades,
            "denominator_counts": self.denominator_counts,
            "event_count": self.event_count,
            "open_exposure_btc": str(self.open_exposure_btc),
            "open_unresolved": self.open_unresolved,
            "report_sha256": self.report_sha256(),
            "settled_equity": str(self.settled_equity) if self.settled_equity is not None else None,
            "terminal_cash": str(self.terminal_cash),
            "terminal_held_btc": str(self.terminal_held_btc),
            "total_net_return_closed": str(self.total_net_return_closed),
            "total_scheduled_decisions": self.total_scheduled_decisions,
            "trial_id": self.trial_id,
        }

    def assert_denominator(self) -> None:
        """Raise if denominator conservation is violated."""
        total = sum(self.denominator_counts.values())
        if total != self.total_scheduled_decisions:
            raise AssertionError(
                f"Denominator violation: counts sum to {total} but "
                f"total_scheduled_decisions={self.total_scheduled_decisions}"
            )
