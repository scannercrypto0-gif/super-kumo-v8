"""
Phase 4 — Append-Only Attempt Ledger
======================================
Narrow caller-owned ledger port, AttemptRecorder-compatible.

Design
------
* Content-addressed, append-only.  Each entry references the previous entry's
  digest (predecessor_digest).
* Deterministic idempotent replay: same inputs yield same entry content.
* Crash recovery: incomplete entries are detectable and reconcilable.
* All attempt states are recorded: REGISTERED, INVALID, FAILED, PENDING,
  COMPLETE, ABANDONED.
* Bounded growth: raises once max_entries is reached rather than silently
  evicting history.
* Compatible with AttemptRecorder's PENDING/INVALID/FAILED/COMPLETE/ABANDONED
  state set (maps REGISTERED -> PENDING on first claim).

This is a LOCAL in-memory ledger for Discoverer V1.  It does NOT import from
unmerged PR #46 (durable_journal.py, trial_holdout.py, temporal_contract.py)
which are on a non-main stacked branch.
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass
from enum import Enum
from typing import List, Optional, Dict

from tools.strategy_discoverer_offline.contracts import _canonical, _digest


# ---------------------------------------------------------------------------
# Attempt state machine
# ---------------------------------------------------------------------------

class AttemptState(str, Enum):
    REGISTERED  = "REGISTERED"   # claimed but not started
    PENDING     = "PENDING"      # in progress
    INVALID     = "INVALID"      # failed validation before execution
    FAILED      = "FAILED"       # execution failed
    COMPLETE    = "COMPLETE"     # successfully finished
    ABANDONED   = "ABANDONED"    # explicitly abandoned


# Valid transitions
_TRANSITIONS = {
    AttemptState.REGISTERED: {AttemptState.PENDING, AttemptState.INVALID, AttemptState.ABANDONED},
    AttemptState.PENDING:    {AttemptState.COMPLETE, AttemptState.FAILED, AttemptState.ABANDONED},
    AttemptState.INVALID:    set(),      # terminal
    AttemptState.FAILED:     set(),      # terminal
    AttemptState.COMPLETE:   set(),      # terminal
    AttemptState.ABANDONED:  set(),      # terminal
}


# ---------------------------------------------------------------------------
# Ledger entry
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class LedgerEntry:
    """
    A single immutable ledger entry.

    entry_index         : 0-based monotonically increasing index
    predecessor_digest  : sha256 of previous entry (or 64 zeros for first)
    attempt_id          : unique attempt identifier
    candidate_id        : associated candidate identifier
    family_id           : family this attempt belongs to
    strategy_digest     : sha256 of the StrategyDefinition payload
    search_plan_digest  : sha256 of the search plan
    nomination_digest   : sha256 of the NominationEvidenceV1
    state               : AttemptState
    reason              : optional human-readable reason for state
    wall_clock_ns       : wall-clock time in nanoseconds (observational only)
    entry_digest        : sha256 of canonical(all fields except entry_digest)
    """
    entry_index: int
    predecessor_digest: str
    attempt_id: str
    candidate_id: str
    family_id: str
    strategy_digest: str
    search_plan_digest: str
    nomination_digest: str
    state: str
    reason: str
    wall_clock_ns: int
    entry_digest: str

    def __post_init__(self):
        AttemptState(self.state)   # validate enum
        for attr in ("predecessor_digest", "strategy_digest", "search_plan_digest",
                     "nomination_digest", "entry_digest"):
            v = getattr(self, attr)
            if not isinstance(v, str) or len(v) != 64 or not all(
                    c in "0123456789abcdef" for c in v):
                raise ValueError(f"{attr} must be 64-char lowercase hex SHA-256")
        if self.entry_index < 0:
            raise ValueError("entry_index must be non-negative")
        if self.wall_clock_ns < 0:
            raise ValueError("wall_clock_ns must be non-negative")
        # Verify entry_digest
        expected = _digest(self._fields_for_digest())
        if self.entry_digest != expected:
            raise ValueError(
                f"entry_digest mismatch for attempt {self.attempt_id}: "
                f"stored={self.entry_digest} computed={expected}"
            )

    def _fields_for_digest(self) -> dict:
        return {
            "entry_index": self.entry_index,
            "predecessor_digest": self.predecessor_digest,
            "attempt_id": self.attempt_id,
            "candidate_id": self.candidate_id,
            "family_id": self.family_id,
            "strategy_digest": self.strategy_digest,
            "search_plan_digest": self.search_plan_digest,
            "nomination_digest": self.nomination_digest,
            "state": self.state,
            "reason": self.reason,
        }
        # NOTE: wall_clock_ns is intentionally excluded from digest — it is
        # observational metadata only; including it would make the digest
        # non-deterministic and break idempotent replay (C-02 fix).

    def to_dict(self) -> dict:
        d = self._fields_for_digest()
        d["entry_digest"] = self.entry_digest
        # wall_clock_ns is observational metadata — not in digest, but persisted for audit
        d["wall_clock_ns"] = self.wall_clock_ns
        return d

    def verify(self) -> bool:
        return self.entry_digest == _digest(self._fields_for_digest())


# ---------------------------------------------------------------------------
# Ledger
# ---------------------------------------------------------------------------

# Sentinel: predecessor_digest for the very first entry
_GENESIS_DIGEST = "0" * 64

# Default maximum entries — protects against unbounded growth
DEFAULT_MAX_ENTRIES = 4096


class DiscovererLedger:
    """
    In-memory append-only attempt ledger for Discoverer V1.

    Thread safety: not thread-safe.  Use one ledger per generator run.

    Crash recovery: the ledger can be reconstructed from its entries list.
    Incomplete attempts (REGISTERED/PENDING without a terminal state) are
    detectable via incomplete_attempts().

    Idempotency: appending the same (attempt_id, state, ...) twice raises
    ValueError — no silent double-counting.
    """

    def __init__(self, max_entries: int = DEFAULT_MAX_ENTRIES):
        self._entries: List[LedgerEntry] = []
        self._seen_attempt_ids: Dict[str, int] = {}   # attempt_id -> entry_index
        self._max_entries = max_entries
        self._head_digest = _GENESIS_DIGEST

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def register(
        self,
        attempt_id: str,
        candidate_id: str,
        family_id: str,
        strategy_digest: str,
        search_plan_digest: str,
        nomination_digest: str,
        reason: str = "",
    ) -> LedgerEntry:
        """
        Register a new attempt.  Initial state = REGISTERED.
        Raises if attempt_id already exists in this ledger.
        Raises if max_entries reached.
        """
        if attempt_id in self._seen_attempt_ids:
            raise ValueError(
                f"Duplicate attempt_id: {attempt_id!r}.  "
                f"Each attempt must have a unique ID."
            )
        return self._append(
            attempt_id=attempt_id,
            candidate_id=candidate_id,
            family_id=family_id,
            strategy_digest=strategy_digest,
            search_plan_digest=search_plan_digest,
            nomination_digest=nomination_digest,
            state=AttemptState.REGISTERED,
            reason=reason,
        )

    def transition(
        self,
        attempt_id: str,
        new_state: AttemptState,
        reason: str = "",
    ) -> LedgerEntry:
        """
        Transition an existing attempt to a new state.

        Raises if attempt_id not found.
        Raises if the transition is invalid.
        Raises if the attempt is already in a terminal state.
        """
        if attempt_id not in self._seen_attempt_ids:
            raise ValueError(f"Unknown attempt_id: {attempt_id!r}")

        # Find the latest entry for this attempt_id
        latest = self._latest_for_attempt(attempt_id)
        current_state = AttemptState(latest.state)

        if new_state not in _TRANSITIONS.get(current_state, set()):
            raise ValueError(
                f"Invalid state transition for attempt {attempt_id!r}: "
                f"{current_state.value} -> {new_state.value}"
            )

        return self._append(
            attempt_id=attempt_id,
            candidate_id=latest.candidate_id,
            family_id=latest.family_id,
            strategy_digest=latest.strategy_digest,
            search_plan_digest=latest.search_plan_digest,
            nomination_digest=latest.nomination_digest,
            state=new_state,
            reason=reason,
        )

    def head_digest(self) -> str:
        """Return the digest of the most recently appended entry."""
        return self._head_digest

    def entries(self) -> List[LedgerEntry]:
        return list(self._entries)

    def entry_count(self) -> int:
        return len(self._entries)

    def summary(self) -> dict:
        """Return census summary of all attempts by state."""
        state_counts: Dict[str, int] = {s.value: 0 for s in AttemptState}
        seen_attempt_ids = set()
        for entry in self._entries:
            seen_attempt_ids.add(entry.attempt_id)
        # Count latest state for each unique attempt
        for attempt_id in seen_attempt_ids:
            latest = self._latest_for_attempt(attempt_id)
            state_counts[latest.state] += 1

        total_attempts = len(seen_attempt_ids)
        terminal_states = {AttemptState.INVALID, AttemptState.FAILED,
                           AttemptState.COMPLETE, AttemptState.ABANDONED}
        incomplete = sum(
            1 for aid in seen_attempt_ids
            if AttemptState(self._latest_for_attempt(aid).state) not in terminal_states
        )

        return {
            "total_attempts": total_attempts,
            "by_state": state_counts,
            "incomplete_attempts": incomplete,
            "entry_count": len(self._entries),
            "head_digest": self._head_digest,
        }

    def incomplete_attempts(self) -> List[str]:
        """Return attempt_ids that are not in a terminal state."""
        terminal_states = {AttemptState.INVALID, AttemptState.FAILED,
                           AttemptState.COMPLETE, AttemptState.ABANDONED}
        result = []
        seen = set()
        for entry in reversed(self._entries):
            if entry.attempt_id not in seen:
                seen.add(entry.attempt_id)
                if AttemptState(entry.state) not in terminal_states:
                    result.append(entry.attempt_id)
        return result

    def verify_chain(self) -> bool:
        """
        Verify the integrity of the entire ledger chain.

        Returns True if all entries verify and predecessor links are correct.
        """
        expected_predecessor = _GENESIS_DIGEST
        for entry in self._entries:
            if not entry.verify():
                return False
            if entry.predecessor_digest != expected_predecessor:
                return False
            expected_predecessor = entry.entry_digest
        return True

    def to_dict_list(self) -> List[dict]:
        return [e.to_dict() for e in self._entries]

    @classmethod
    def from_dict_list(cls, entries_data: List[dict],
                       max_entries: int = DEFAULT_MAX_ENTRIES) -> "DiscovererLedger":
        """Reconstruct ledger from serialised entries (for crash recovery)."""
        ledger = cls(max_entries=max_entries)
        for entry_data in entries_data:
            entry = LedgerEntry(**entry_data)
            if not entry.verify():
                raise ValueError(
                    f"Integrity failure in replayed entry {entry.entry_index}: "
                    f"attempt_id={entry.attempt_id!r}"
                )
            # Verify predecessor
            if entry.predecessor_digest != ledger._head_digest:
                raise ValueError(
                    f"Predecessor mismatch at entry {entry.entry_index}: "
                    f"expected {ledger._head_digest!r} got {entry.predecessor_digest!r}"
                )
            if entry.entry_index != len(ledger._entries):
                raise ValueError(
                    f"Entry index mismatch: expected {len(ledger._entries)} "
                    f"got {entry.entry_index}"
                )
            ledger._entries.append(entry)
            ledger._seen_attempt_ids[entry.attempt_id] = entry.entry_index
            ledger._head_digest = entry.entry_digest
        return ledger

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _append(
        self,
        attempt_id: str,
        candidate_id: str,
        family_id: str,
        strategy_digest: str,
        search_plan_digest: str,
        nomination_digest: str,
        state: AttemptState,
        reason: str,
    ) -> LedgerEntry:
        if len(self._entries) >= self._max_entries:
            raise ValueError(
                f"Ledger reached max_entries={self._max_entries}. "
                f"Create a new ledger for additional attempts."
            )

        entry_index = len(self._entries)
        wall_clock_ns = time.time_ns()

        entry = LedgerEntry(
            entry_index=entry_index,
            predecessor_digest=self._head_digest,
            attempt_id=attempt_id,
            candidate_id=candidate_id,
            family_id=family_id,
            strategy_digest=strategy_digest,
            search_plan_digest=search_plan_digest,
            nomination_digest=nomination_digest,
            state=state.value,
            reason=reason,
            wall_clock_ns=wall_clock_ns,
            entry_digest=_digest({
                "entry_index": entry_index,
                "predecessor_digest": self._head_digest,
                "attempt_id": attempt_id,
                "candidate_id": candidate_id,
                "family_id": family_id,
                "strategy_digest": strategy_digest,
                "search_plan_digest": search_plan_digest,
                "nomination_digest": nomination_digest,
                "state": state.value,
                "reason": reason,
                # wall_clock_ns intentionally excluded (C-02 fix):
                # observational metadata only — must not affect digest
            }),
        )

        self._entries.append(entry)
        self._seen_attempt_ids[attempt_id] = entry_index
        self._head_digest = entry.entry_digest
        return entry

    def _latest_for_attempt(self, attempt_id: str) -> LedgerEntry:
        """Return the most recent ledger entry for the given attempt_id."""
        # Scan in reverse for efficiency
        for entry in reversed(self._entries):
            if entry.attempt_id == attempt_id:
                return entry
        raise KeyError(f"attempt_id not found: {attempt_id!r}")
