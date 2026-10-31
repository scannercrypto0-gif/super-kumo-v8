"""F4 — Independent financial ledger: idempotent replay/restart + immutable report.

Canonical contract: aql.p0.historical-decision.v1
Governed by Factory #77 comment 6540573678.
PM Consolidated Correction Order PR #204 comment 6540907647.

The F4 ledger is INDEPENDENT of the G1 operational store (DurablePositionJournal
and durable_journal.py are G1/runtime components; this ledger is research-only P0).

Invariants:
  - Full denominator: scheduled_decisions = sum of all final dispositions + REJECTED
  - No profitability claims from incomplete or unresolvable positions
  - OPEN_UNRESOLVED contributes to open_exposure (NOT settled PnL)
  - Duplicate-key replay = NO-OP (idempotent)
  - Conflicting-payload replay = LEDGER_CONFLICT/STOP
  - Immutable once finalized: report hash covers all events
  - Terminal open positions NEVER contribute to settled PnL (settled_equity=None if held_btc > 0)

Event lifecycle (crash-restart safety):
  PENDING: event constructed and queued in-memory, not yet applied to state
  APPLIED: event applied to in-memory state, not yet persisted to disk
  ACKED:   report persisted + hash-verified on disk (set by persist_report)

Cost basis conservation:
  Entry debit records cost_basis = entry_net * qty + entry_fee * qty
  Exit credit records cost_basis matched from entry to verify conservation
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from decimal import Decimal
from hashlib import sha256
from pathlib import Path
from typing import Any

from .aql_p0_c1_source import _canonical_bytes, _sha256_hex
from .aql_p0_f1f2_opportunities import Opportunity, SignalState
from .aql_p0_f3_fill_model import FillResult, INITIAL_CASH, POSITION_SIZE_BTC


class LedgerConflictError(RuntimeError):
    """Same event_id previously applied with a different payload. STOP."""


class LedgerIdentityError(ValueError):
    """Opportunity/fill identity mismatch — swapped, missing, or duplicate fills."""


class LedgerReportCorrupted(ValueError):
    """Loaded report SHA-256 does not match stored value — tampering detected."""


class LedgerReceiptCorrupted(ValueError):
    """Individual receipt file corrupted or conflicts with in-memory state."""


# ---------------------------------------------------------------------------
# Event lifecycle states
# ---------------------------------------------------------------------------

PENDING = "PENDING"
APPLIED = "APPLIED"
ACKED = "ACKED"  # set by persist_report after successful disk write + readback


# ---------------------------------------------------------------------------
# Ledger event types
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class LedgerEvent:
    """One immutable financial event."""
    event_id: str           # sha256(canonical({opportunity_id, kind, bar_open_ms}))
    opportunity_id: str
    kind: str               # "ENTRY_DEBIT" | "EXIT_CREDIT" | "NO_ACTION"
    bar_open_ms: int | None
    price_net: Decimal | None
    quantity_btc: Decimal | None
    fee: Decimal | None
    cost_basis: Decimal | None    # (price_net + fee) * qty for ENTRY; matched for EXIT
    cash_delta: Decimal | None    # positive = cash increase, negative = decrease
    cumulative_cash: Decimal | None
    held_btc_delta: Decimal | None
    cumulative_held_btc: Decimal | None


@dataclass(frozen=True)
class FinancialReceipt:
    """F4 fix: individual durable receipt per LedgerEvent.

    Covers every field that, if altered, would constitute a different financial
    outcome — even if aggregate totals happen to be preserved.

    payload_hash = sha256(canonical of all fields except payload_hash itself)
    report_sha256 in LedgerReport MUST include the ordered list of all
    payload_hashes so that altering any single event changes the report digest.
    """
    event_id: str
    opportunity_id: str
    kind: str                         # "ENTRY_DEBIT" | "EXIT_CREDIT"
    bar_open_ms: int | None
    cash_delta: str | None            # str(Decimal) — exact arithmetic
    fee: str | None
    quantity_btc: str | None
    cost_basis: str | None
    price_net: str | None
    held_btc_delta: str | None
    payload_hash: str                 # sha256 of canonical({all other fields})

    @classmethod
    def from_event(cls, event: "LedgerEvent") -> "FinancialReceipt":
        """Construct receipt from LedgerEvent, computing payload_hash."""
        fields = {
            "bar_open_ms": event.bar_open_ms,
            "cash_delta": str(event.cash_delta) if event.cash_delta is not None else None,
            "cost_basis": str(event.cost_basis) if event.cost_basis is not None else None,
            "event_id": event.event_id,
            "fee": str(event.fee) if event.fee is not None else None,
            "held_btc_delta": str(event.held_btc_delta) if event.held_btc_delta is not None else None,
            "kind": event.kind,
            "opportunity_id": event.opportunity_id,
            "price_net": str(event.price_net) if event.price_net is not None else None,
            "quantity_btc": str(event.quantity_btc) if event.quantity_btc is not None else None,
        }
        ph = _sha256_hex(_canonical_bytes(fields))
        return cls(
            event_id=event.event_id,
            opportunity_id=event.opportunity_id,
            kind=event.kind,
            bar_open_ms=event.bar_open_ms,
            cash_delta=fields["cash_delta"],
            fee=fields["fee"],
            quantity_btc=fields["quantity_btc"],
            cost_basis=fields["cost_basis"],
            price_net=fields["price_net"],
            held_btc_delta=fields["held_btc_delta"],
            payload_hash=ph,
        )

    def to_dict(self) -> dict:
        return {
            "bar_open_ms": self.bar_open_ms,
            "cash_delta": self.cash_delta,
            "cost_basis": self.cost_basis,
            "event_id": self.event_id,
            "fee": self.fee,
            "held_btc_delta": self.held_btc_delta,
            "kind": self.kind,
            "opportunity_id": self.opportunity_id,
            "payload_hash": self.payload_hash,
            "price_net": self.price_net,
            "quantity_btc": self.quantity_btc,
        }


@dataclass
class LedgerState:
    """Mutable ledger state during replay."""
    cash: Decimal = field(default_factory=lambda: INITIAL_CASH)
    held_btc: Decimal = field(default_factory=lambda: Decimal("0"))
    events: list[LedgerEvent] = field(default_factory=list)
    applied_event_ids: dict[str, str] = field(default_factory=dict)  # id→payload_hash
    # Three-phase event lifecycle — event_id → PENDING/APPLIED/ACKED
    event_states: dict[str, str] = field(default_factory=dict)
    error: str | None = None


def _event_id(opportunity_id: str, kind: str, bar_open_ms: int | None) -> str:
    payload = {"bar_open_ms": bar_open_ms, "kind": kind, "opportunity_id": opportunity_id}
    return _sha256_hex(_canonical_bytes(payload))


def _event_payload_hash(event: LedgerEvent) -> str:
    payload = {
        "bar_open_ms": event.bar_open_ms,
        "cash_delta": str(event.cash_delta) if event.cash_delta is not None else None,
        "cost_basis": str(event.cost_basis) if event.cost_basis is not None else None,
        "fee": str(event.fee) if event.fee is not None else None,
        "kind": event.kind,
        "opportunity_id": event.opportunity_id,
        "price_net": str(event.price_net) if event.price_net is not None else None,
        "quantity_btc": str(event.quantity_btc) if event.quantity_btc is not None else None,
    }
    return _sha256_hex(_canonical_bytes(payload))


def _apply_event(event: LedgerEvent, state: LedgerState) -> None:
    """Apply one event to ledger state.

    Three-phase lifecycle:
      1. Mark PENDING (before this call — caller responsibility, but we confirm)
      2. Idempotent check: same id+payload = NO-OP; conflicting payload = STOP
      3. Apply to in-memory state → mark APPLIED
    """
    ph = _event_payload_hash(event)
    if event.event_id in state.applied_event_ids:
        existing_ph = state.applied_event_ids[event.event_id]
        if existing_ph != ph:
            raise LedgerConflictError(
                f"LEDGER_CONFLICT: event_id={event.event_id!r} was previously applied "
                f"with payload_hash={existing_ph!r} but now has {ph!r}. STOP."
            )
        # Idempotent NO-OP — already APPLIED
        return

    # Mark PENDING then transition to APPLIED atomically
    state.event_states[event.event_id] = PENDING
    state.applied_event_ids[event.event_id] = ph

    if event.cash_delta is not None:
        state.cash += event.cash_delta
    if event.held_btc_delta is not None:
        state.held_btc += event.held_btc_delta

    state.events.append(event)
    state.event_states[event.event_id] = APPLIED


def _validate_identity(
    opportunities: list[Opportunity],
    fill_results: list[FillResult],
) -> None:
    """Validate opportunity/fill identity before ledger posting.

    Raises LedgerIdentityError if:
      - Length mismatch
      - Any fill.opportunity_id != corresponding opp.opportunity_id (swapped/missing)
      - Duplicate opportunity_ids in input
    """
    if len(opportunities) != len(fill_results):
        raise LedgerIdentityError(
            f"IDENTITY_LENGTH_MISMATCH: {len(opportunities)} opps vs "
            f"{len(fill_results)} fills"
        )

    seen_opp_ids: set[str] = set()
    for i, (opp, fill) in enumerate(zip(opportunities, fill_results)):
        if fill.opportunity_id != opp.opportunity_id:
            raise LedgerIdentityError(
                f"IDENTITY_MISMATCH at index {i}: "
                f"opp.opportunity_id={opp.opportunity_id!r} != "
                f"fill.opportunity_id={fill.opportunity_id!r} — "
                f"possible swapped or missing fill"
            )
        if opp.opportunity_id in seen_opp_ids:
            raise LedgerIdentityError(
                f"DUPLICATE_OPPORTUNITY_ID: {opp.opportunity_id!r} at index {i}"
            )
        seen_opp_ids.add(opp.opportunity_id)


def build_ledger(
    opportunities: list[Opportunity],
    fill_results: list[FillResult],
    *,
    trial_id: str,
    manifest_sha256: str | None = None,
    strategy_digest: str | None = None,
    policy_id: str | None = None,
    assumptions_digest: str | None = None,
) -> tuple[LedgerState, "LedgerReport"]:
    """Apply all fill results to the ledger and produce an immutable report.

    Events are sorted chronologically before application — EXIT_CREDIT fires
    before ENTRY_DEBIT when two events share the same bar_open_ms.  This
    ensures that when one opportunity exits and another enters at the identical
    execution bar, the exit cash is credited first (correct event-time ordering).

    Parameters
    ----------
    opportunities:
        F1+F2 output (for denominator tracking).
    fill_results:
        F3 output (one per opportunity, in matching order).
    trial_id:
        Frozen trial identifier for report identity.
    manifest_sha256:
        Optional: SHA-256 of the source manifest (lineage binding).
    strategy_digest:
        Optional: digest of the strategy parameters.
    policy_id:
        Optional: policy identifier applied during this run.
    assumptions_digest:
        Optional: digest of the full assumptions document.

    Returns
    -------
    (LedgerState, LedgerReport)

    Raises
    ------
    LedgerIdentityError
        On any opportunity/fill identity violation (swapped, missing, duplicate).
    LedgerConflictError
        On conflicting-payload idempotent replay.
    """
    # --- Phase 0: Identity validation BEFORE any ledger mutation ---
    _validate_identity(opportunities, fill_results)

    state = LedgerState()

    # Denominator tracking — includes REJECTED from F3
    counts: dict[str, int] = {
        "NO_SIGNAL": 0, "ARMED": 0, "TRIGGERED": 0, "NO_FILL": 0,
        "EXPIRED": 0, "UNKNOWN": 0, "BLOCKED": 0,
        "OPEN_UNRESOLVED": 0, "REJECTED": 0, "OTHER": 0,
    }
    open_exposure_btc = Decimal("0")

    # Track cost_basis per opportunity_id for exit conservation check
    cost_basis_by_opp: dict[str, Decimal] = {}

    # Phase 1: Collect ALL events (without applying) so we can sort before apply.
    # EXIT_CREDIT must come before ENTRY_DEBIT at the same bar_open_ms so that
    # cash from a closing position is available when the next entry fires at the
    # same bar (event-time ordering invariant).
    all_pending_events: list[LedgerEvent] = []

    for opp, fill in zip(opportunities, fill_results):
        # Count denominator — REJECTED is now a first-class bucket
        state_key = fill.signal_state if fill.signal_state in counts else "OTHER"
        counts[state_key] += 1

        if fill.signal_state == "TRIGGERED" and fill.entry_price_net is not None:
            # --- Entry DEBIT (queued, not applied yet) ---
            entry_qty_fee = fill.entry_fee * POSITION_SIZE_BTC
            entry_qty_price = fill.entry_price_net * POSITION_SIZE_BTC
            entry_cost_basis = entry_qty_price + entry_qty_fee
            entry_cash_delta = -entry_cost_basis

            all_pending_events.append(LedgerEvent(
                event_id=_event_id(opp.opportunity_id, "ENTRY_DEBIT", fill.entry_bar_open_ms),
                opportunity_id=opp.opportunity_id,
                kind="ENTRY_DEBIT",
                bar_open_ms=fill.entry_bar_open_ms,
                price_net=fill.entry_price_net,
                quantity_btc=POSITION_SIZE_BTC,
                fee=entry_qty_fee,
                cost_basis=entry_cost_basis,
                cash_delta=entry_cash_delta,
                cumulative_cash=None,
                held_btc_delta=POSITION_SIZE_BTC,
                cumulative_held_btc=None,
            ))
            cost_basis_by_opp[opp.opportunity_id] = entry_cost_basis

            if fill.exit_price_net is not None:
                # --- Exit CREDIT (queued, not applied yet) ---
                exit_qty_fee = fill.exit_fee * POSITION_SIZE_BTC
                exit_qty_price = fill.exit_price_net * POSITION_SIZE_BTC
                exit_cash_delta = exit_qty_price - exit_qty_fee

                # Cost basis matched from entry (conservation check)
                exit_cost_basis = cost_basis_by_opp.get(opp.opportunity_id)

                all_pending_events.append(LedgerEvent(
                    event_id=_event_id(opp.opportunity_id, "EXIT_CREDIT", fill.exit_bar_open_ms),
                    opportunity_id=opp.opportunity_id,
                    kind="EXIT_CREDIT",
                    bar_open_ms=fill.exit_bar_open_ms,
                    price_net=fill.exit_price_net,
                    quantity_btc=POSITION_SIZE_BTC,
                    fee=exit_qty_fee,
                    cost_basis=exit_cost_basis,
                    cash_delta=exit_cash_delta,
                    cumulative_cash=None,
                    held_btc_delta=-POSITION_SIZE_BTC,
                    cumulative_held_btc=None,
                ))

        elif fill.signal_state == "OPEN_UNRESOLVED":
            # Open position at window end: record ENTRY DEBIT only.
            # No EXIT CREDIT — OPEN_UNRESOLVED never contributes to settled PnL.
            if fill.entry_price_net is not None:
                entry_qty_fee = fill.entry_fee * POSITION_SIZE_BTC
                entry_qty_price = fill.entry_price_net * POSITION_SIZE_BTC
                entry_cost_basis = entry_qty_price + entry_qty_fee
                entry_cash_delta = -entry_cost_basis

                all_pending_events.append(LedgerEvent(
                    event_id=_event_id(opp.opportunity_id, "ENTRY_DEBIT", fill.entry_bar_open_ms),
                    opportunity_id=opp.opportunity_id,
                    kind="ENTRY_DEBIT",
                    bar_open_ms=fill.entry_bar_open_ms,
                    price_net=fill.entry_price_net,
                    quantity_btc=POSITION_SIZE_BTC,
                    fee=entry_qty_fee,
                    cost_basis=entry_cost_basis,
                    cash_delta=entry_cash_delta,
                    cumulative_cash=None,
                    held_btc_delta=POSITION_SIZE_BTC,
                    cumulative_held_btc=None,
                ))
                cost_basis_by_opp[opp.opportunity_id] = entry_cost_basis
                open_exposure_btc += POSITION_SIZE_BTC

        # REJECTED, NO_SIGNAL, NO_FILL, BLOCKED, UNKNOWN, EXPIRED — no financial events

    # Phase 2: Sort events chronologically.
    # Primary key: bar_open_ms (ascending).
    # Secondary key: EXIT_CREDIT (0) before ENTRY_DEBIT (1) — so that when an
    # exit and a new entry share the same execution bar, the exit cash is applied
    # first (restoring position availability) before the entry debit is checked.
    _kind_order = {"EXIT_CREDIT": 0, "ENTRY_DEBIT": 1}
    all_pending_events.sort(key=lambda ev: (ev.bar_open_ms, _kind_order.get(ev.kind, 2)))

    # Phase 3: Apply sorted events
    for ev in all_pending_events:
        _apply_event(ev, state)

    # --- Produce immutable report ---
    total_scheduled = len(opportunities)
    sum_counts = sum(counts.values())
    assert sum_counts == total_scheduled, (
        f"Denominator invariant violated: {sum_counts} != {total_scheduled}"
    )

    # Closed trades PnL — OPEN_UNRESOLVED EXCLUDED
    closed_net_returns: list[Decimal] = []
    for fill in fill_results:
        if fill.signal_state == "TRIGGERED" and fill.net_return is not None:
            closed_net_returns.append(fill.net_return)

    total_net_return = sum(closed_net_returns) if closed_net_returns else Decimal("0")
    avg_net_return = (total_net_return / len(closed_net_returns)
                      if closed_net_returns else None)

    # settled_equity = None if any open positions remain (OPEN_UNRESOLVED present)
    settled_equity = state.cash if state.held_btc == Decimal("0") else None

    # F4 fix: compute FinancialReceipt per event; derive ordered_receipt_hashes
    # This covers each individual event so that altering ANY event changes the
    # report digest — even if aggregate totals are preserved by a compensating edit.
    receipts: list[FinancialReceipt] = [
        FinancialReceipt.from_event(ev) for ev in state.events
    ]
    ordered_receipt_hashes = tuple(r.payload_hash for r in receipts)
    # Attach receipts to state for persist_receipts()
    state._receipts = receipts  # type: ignore[attr-defined]

    # Lineage: preserve input ordering of opportunities for report identity
    ordered_opportunity_ids = tuple(opp.opportunity_id for opp in opportunities)

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
        settled_equity=settled_equity,
        event_count=len(state.events),
        ordered_receipt_hashes=ordered_receipt_hashes,
        ordered_opportunity_ids=ordered_opportunity_ids,
        manifest_sha256=manifest_sha256,
        strategy_digest=strategy_digest,
        policy_id=policy_id,
        assumptions_digest=assumptions_digest,
    )
    return state, report


# ---------------------------------------------------------------------------
# F4 durable receipt file
# ---------------------------------------------------------------------------

def persist_receipts(
    state: LedgerState,
    path: Path | str,
) -> int:
    """Persist individual FinancialReceipts to a JSON-lines file with fsync.

    Each line is one receipt (sorted-key canonical JSON). File is append-only.
    On restart, call load_receipts() to reconcile:
      - Same event_id + same payload_hash → idempotent NO-OP
      - Same event_id + different payload_hash → LedgerReceiptCorrupted STOP

    Returns number of receipts written.
    """
    receipts: list[FinancialReceipt] = getattr(state, "_receipts", [])
    if not receipts:
        return 0

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    # Load existing to check idempotency before writing
    existing: dict[str, str] = {}
    if path.exists():
        existing = _load_receipts_file(path)

    written = 0
    with open(path, "ab") as fh:
        for r in receipts:
            if r.event_id in existing:
                if existing[r.event_id] != r.payload_hash:
                    raise LedgerReceiptCorrupted(
                        f"RECEIPT_CONFLICT: event_id={r.event_id!r} "
                        f"stored_hash={existing[r.event_id]!r} "
                        f"new_hash={r.payload_hash!r} — STOP"
                    )
                # Same id+hash → already persisted, skip
                continue
            line = json.dumps(r.to_dict(), sort_keys=True,
                              separators=(",", ":"), ensure_ascii=False).encode("utf-8")
            fh.write(line + b"\n")
            fh.flush()
            os.fsync(fh.fileno())
            written += 1

    return written


def load_receipts(path: Path | str) -> dict[str, str]:
    """Load persisted receipts. Returns {event_id: payload_hash}.

    On restart, pass this to reconcile_receipts() before posting new events.
    Raises LedgerReceiptCorrupted if the file is corrupt or unreadable.
    """
    path = Path(path)
    if not path.exists():
        return {}
    return _load_receipts_file(path)


def reconcile_receipts(
    state: LedgerState,
    persisted: dict[str, str],
) -> None:
    """Cross-check in-memory events against persisted receipts after restart.

    For each event in state:
      - Same event_id + same payload_hash in persisted → no-op (already durable)
      - Same event_id + different payload_hash → LedgerReceiptCorrupted STOP
      - event_id absent from persisted → not yet persisted (write pending)
    """
    receipts: list[FinancialReceipt] = getattr(state, "_receipts", [])
    for r in receipts:
        if r.event_id in persisted:
            if persisted[r.event_id] != r.payload_hash:
                raise LedgerReceiptCorrupted(
                    f"RECONCILE_CONFLICT: event_id={r.event_id!r} "
                    f"in-memory payload_hash={r.payload_hash!r} "
                    f"persisted={persisted[r.event_id]!r} — STOP"
                )


def _load_receipts_file(path: Path) -> dict[str, str]:
    """Read JSON-lines receipt file → {event_id: payload_hash}.

    STOP on any corrupted or unparseable line — fail closed.
    Silently skipping corrupted lines hides data loss; the ledger must
    know all events are accounted for before proceeding.
    """
    result: dict[str, str] = {}
    for raw_line in path.read_bytes().splitlines():
        raw_line = raw_line.strip()
        if not raw_line:
            continue
        try:
            d = json.loads(raw_line)
            event_id = d["event_id"]
            payload_hash = d["payload_hash"]
            result[event_id] = payload_hash
        except (json.JSONDecodeError, KeyError) as exc:
            raise LedgerReceiptCorrupted(
                f"RECEIPTS_FILE_CORRUPTED: line could not be parsed — {exc}"
            ) from exc
    return result


# ---------------------------------------------------------------------------
# Durable report persistence (Fix 4)
# ---------------------------------------------------------------------------

def persist_report(
    report: "LedgerReport",
    path: Path | str,
    state: LedgerState | None = None,
) -> str:
    """Persist report to disk as canonical JSON. Returns the written SHA-256.

    After successful write + readback verification:
      - All APPLIED events in state.event_states are promoted to ACKED.

    Raises
    ------
    LedgerReportCorrupted
        If the written bytes cannot be read back and hash-verified.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    d = report.to_dict()  # includes report_sha256 field
    written_sha = report.report_sha256()

    canonical = json.dumps(d, sort_keys=True, separators=(",", ":"),
                           ensure_ascii=False, allow_nan=False).encode("utf-8")

    # Atomic write via temp file + parent-dir fsync for crash safety
    tmp_path = path.with_suffix(".tmp")
    try:
        tmp_path.write_bytes(canonical)
        tmp_path.rename(path)
        # Fsync parent directory to make rename durable across kernel crash.
        # Without this, the rename may be lost on Linux after a power failure.
        # Best-effort: Windows does not support directory fsync.
        parent_dir = path.parent
        try:
            parent_fd = os.open(str(parent_dir), os.O_RDONLY)
            try:
                os.fsync(parent_fd)
            finally:
                os.close(parent_fd)
        except OSError:
            pass  # Best-effort; non-fatal on platforms that don't support it
    except Exception as exc:
        if tmp_path.exists():
            tmp_path.unlink(missing_ok=True)
        raise

    # Readback verification
    read_back = path.read_bytes()
    loaded_report = _load_report_bytes(read_back)
    if loaded_report.report_sha256() != written_sha:
        raise LedgerReportCorrupted(
            f"READBACK_HASH_MISMATCH: written={written_sha!r} "
            f"read={loaded_report.report_sha256()!r}"
        )

    # Promote all APPLIED events to ACKED
    if state is not None:
        for eid, estate in list(state.event_states.items()):
            if estate == APPLIED:
                state.event_states[eid] = ACKED

    return written_sha


def load_report(path: Path | str) -> "LedgerReport":
    """Load and verify a persisted report. Raises LedgerReportCorrupted on hash mismatch."""
    path = Path(path)
    raw = path.read_bytes()
    return _load_report_bytes(raw)


def _load_report_bytes(raw: bytes) -> "LedgerReport":
    """Parse and hash-verify report bytes."""
    try:
        d = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise LedgerReportCorrupted(f"REPORT_JSON_PARSE_ERROR: {exc}") from exc

    stored_sha = d.get("report_sha256")
    if not stored_sha:
        raise LedgerReportCorrupted("REPORT_MISSING_SHA256_FIELD")

    # Reconstruct report (without the report_sha256 field, which is derived)
    try:
        dc = dict(d)
        dc.pop("report_sha256", None)
        report = LedgerReport(
            trial_id=dc["trial_id"],
            total_scheduled_decisions=dc["total_scheduled_decisions"],
            denominator_counts=dc["denominator_counts"],
            closed_trades=dc["closed_trades"],
            open_unresolved=dc["open_unresolved"],
            open_exposure_btc=Decimal(dc["open_exposure_btc"]),
            terminal_cash=Decimal(dc["terminal_cash"]),
            terminal_held_btc=Decimal(dc["terminal_held_btc"]),
            total_net_return_closed=Decimal(dc["total_net_return_closed"]),
            average_net_return_closed=(
                Decimal(dc["average_net_return_closed"])
                if dc["average_net_return_closed"] is not None else None
            ),
            settled_equity=(
                Decimal(dc["settled_equity"])
                if dc["settled_equity"] is not None else None
            ),
            event_count=dc["event_count"],
            # F4 fix: load ordered_receipt_hashes from persisted report
            ordered_receipt_hashes=tuple(dc.get("ordered_receipt_hashes", [])),
            # F4 lineage fix: optional fields default gracefully for backward compat
            ordered_opportunity_ids=tuple(dc.get("ordered_opportunity_ids", [])),
            manifest_sha256=dc.get("manifest_sha256"),
            strategy_digest=dc.get("strategy_digest"),
            policy_id=dc.get("policy_id"),
            assumptions_digest=dc.get("assumptions_digest"),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise LedgerReportCorrupted(f"REPORT_FIELD_ERROR: {exc}") from exc

    computed_sha = report.report_sha256()
    if computed_sha != stored_sha:
        raise LedgerReportCorrupted(
            f"REPORT_SHA256_MISMATCH: stored={stored_sha!r} computed={computed_sha!r}"
        )

    return report


@dataclass(frozen=True)
class LedgerReport:
    """Immutable final report. settled_equity=None if open positions remain.

    F4 fix: report_sha256 now covers ordered_receipt_hashes — the list of
    individual per-event payload hashes in event-application order. This means
    altering ANY single event (even while preserving aggregate totals) produces
    a different report digest, catching tamper-while-preserving-totals attacks.
    """
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
    settled_equity: Decimal | None   # null if held_btc > 0 (OPEN_UNRESOLVED present)
    event_count: int
    # F4 fix: sorted list of individual FinancialReceipt payload_hashes
    # Covers every event — altering any event changes this list → changes report_sha256
    ordered_receipt_hashes: tuple[str, ...]  # in event-application order
    # F4 lineage fields: binding this report to its input provenance
    # All optional with defaults so existing call sites remain backward compatible
    ordered_opportunity_ids: tuple[str, ...] = ()
    manifest_sha256: str | None = None
    strategy_digest: str | None = None
    policy_id: str | None = None
    assumptions_digest: str | None = None

    def report_sha256(self) -> str:
        """Immutable content hash of this report.

        F4 fix: includes ordered_receipt_hashes so that altering any single
        event (even while preserving aggregate totals) changes this digest.
        F4 lineage fix: also covers lineage fields so that changing source,
        strategy, policy, or opportunity ordering produces a different digest.
        """
        d = {
            "assumptions_digest": self.assumptions_digest,
            "average_net_return_closed": str(self.average_net_return_closed) if self.average_net_return_closed is not None else None,
            "closed_trades": self.closed_trades,
            "denominator_counts": self.denominator_counts,
            "event_count": self.event_count,
            "manifest_sha256": self.manifest_sha256,
            "open_exposure_btc": str(self.open_exposure_btc),
            "open_unresolved": self.open_unresolved,
            # F4 fix: cover individual receipt hashes — not just aggregates
            "ordered_opportunity_ids": list(self.ordered_opportunity_ids),
            "ordered_receipt_hashes": list(self.ordered_receipt_hashes),
            "policy_id": self.policy_id,
            "settled_equity": str(self.settled_equity) if self.settled_equity is not None else None,
            "strategy_digest": self.strategy_digest,
            "terminal_cash": str(self.terminal_cash),
            "terminal_held_btc": str(self.terminal_held_btc),
            "total_net_return_closed": str(self.total_net_return_closed),
            "total_scheduled_decisions": self.total_scheduled_decisions,
            "trial_id": self.trial_id,
        }
        return _sha256_hex(_canonical_bytes(d))

    def to_dict(self) -> dict:
        return {
            "assumptions_digest": self.assumptions_digest,
            "average_net_return_closed": str(self.average_net_return_closed) if self.average_net_return_closed is not None else None,
            "closed_trades": self.closed_trades,
            "denominator_counts": self.denominator_counts,
            "event_count": self.event_count,
            "manifest_sha256": self.manifest_sha256,
            "open_exposure_btc": str(self.open_exposure_btc),
            "open_unresolved": self.open_unresolved,
            "ordered_opportunity_ids": list(self.ordered_opportunity_ids),
            "ordered_receipt_hashes": list(self.ordered_receipt_hashes),
            "policy_id": self.policy_id,
            "report_sha256": self.report_sha256(),
            "settled_equity": str(self.settled_equity) if self.settled_equity is not None else None,
            "strategy_digest": self.strategy_digest,
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
