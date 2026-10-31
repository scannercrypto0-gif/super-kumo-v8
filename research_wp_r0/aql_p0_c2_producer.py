"""C2 — Deterministic decision producer: identities, ACK/restart idempotency, readback.

Canonical contract: aql.p0.historical-decision.v1
Governed by Core #180 comment 6540572768 (C2 execution task).
PM Consolidated Correction Order PR #204 comment 6541273650 — C2 durable journal fix.

C2 receives the validated P0SourceManifest from C1 and produces one immutable
decision_envelope per scheduled 15m decision window, with:
  - deterministic opportunity_id and producer_event_id (stable across restarts)
  - per-decision prefix integrity (own cutoff, own bar digest — no full-window lookahead)
  - RETROSPECTIVE_NON_PIT availability mode throughout
  - explicit BLOCKED/UNKNOWN for any prefix integrity failure (fail closed)
  - idempotent restart: same key + same digest = NO-OP; same key + different digest = CONFLICT/STOP
  - durable journal: JSON-lines file, fsync after each write, readback before APPLIED
    (replaces prior in-memory dict — fixes C2 blocker: no crash recovery across processes)

NO strategy logic here — C2 produces envelopes; F1 consumes them.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Any

from .aql_p0_c1_source import (
    SCHEMA,
    PROJECT_ID,
    SYMBOL,
    INTERVAL_MS,
    WINDOW_START_MS,
    WINDOW_END_EXCLUSIVE_MS,
    P0SourceManifest,
    P0Bar,
    _canonical_bytes,
    _sha256_hex,
)


# ---------------------------------------------------------------------------
# Strategy pins (frozen for this P0 trial)
# ---------------------------------------------------------------------------

STRATEGY_ID = "SF_BREAKOUT_BASE_20_10_DEV_v1"
STRATEGY_VERSION = "1"
POLICY_ID = "P0-DEV-RETROSPECTIVE-v1"

# Entry requires at least 20 prior completed bars for lookback
ENTRY_LOOKBACK = 20
# Exit requires at least 10 prior completed bars for lookback
EXIT_LOOKBACK = 10
# Minimum bars needed before first evaluable decision
MIN_PREFIX_BARS = ENTRY_LOOKBACK

# Source lag + execution latency assumptions (documented, not verified)
SOURCE_LAG_ASSUMPTION_MS = 1_000    # 1 s
LATENCY_ASSUMPTION_MS = 1_000       # 1 s


# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------

class C2ConflictError(RuntimeError):
    """Same producer_event_id was previously produced with a different digest. STOP."""


@dataclass(frozen=True)
class DecisionEnvelope:
    """One immutable per-decision output from C2 → Factory handoff."""
    schema: str
    trial_id: str
    run_manifest_sha256: str
    dataset_id: str
    dataset_version: int
    strategy_id: str
    strategy_version: str
    strategy_digest: str
    strategy_instance_id: str
    account_id: str
    opportunity_id: str           # deterministic
    decision_ms: int              # modeled evaluation instant
    decision_cutoff_ms: int       # >= final feature bar_close_ms+1
    prefix_start_ms: int
    prefix_end_exclusive_ms: int
    prefix_bar_checksums_sha256: str
    feature_policy_version: str
    gap_inventory_sha256: str
    correction_lineage_sha256: str
    coverage_status: str          # "COMPLETE" | "INCOMPLETE" | "UNKNOWN"
    availability_mode: str        # always "RETROSPECTIVE_NON_PIT"
    source_lag_assumption_ms: int
    latency_assumption_ms: int
    producer_event_id: str        # deterministic
    input_disposition: str        # "EVALUABLE_RETROSPECTIVE" | "BLOCKED" | "UNKNOWN"
    reason_code: str | None
    envelope_sha256: str          # sha256(canonical(envelope without this field))


@dataclass
class ConsumerJournalEntry:
    """Durable consumer journal record (PENDING→APPLIED→ACKED)."""
    producer_event_id: str
    opportunity_id: str
    envelope_sha256: str
    state: str    # "PENDING" | "APPLIED" | "ACKED"


# ---------------------------------------------------------------------------
# Durable Journal (file-backed, crash-safe)
# ---------------------------------------------------------------------------

class DurableJournal:
    """JSON-lines file-backed journal with fsync-after-write and readback.

    Lifecycle per entry:
      PENDING  → written + fsynced to disk
      APPLIED  → only after successful readback verification
      ACKED    → confirmed by downstream consumer

    Crash recovery:
      load_journal(path) reconstructs state from disk.
      Same producer_event_id + same digest → NO-OP (idempotent).
      Same producer_event_id + different digest → C2ConflictError STOP.
    """

    def __init__(self, path: Path) -> None:
        self._path = Path(path)
        self._entries: dict[str, ConsumerJournalEntry] = {}
        # Load existing entries if file exists
        if self._path.exists():
            self._entries = _load_journal_file(self._path)

    @property
    def entries(self) -> dict[str, ConsumerJournalEntry]:
        return self._entries

    def write_pending(
        self,
        producer_event_id: str,
        opportunity_id: str,
        envelope_sha256: str,
    ) -> ConsumerJournalEntry:
        """Append PENDING entry to disk + fsync. Returns the entry.

        Idempotent: same id + same digest → returns existing entry unchanged.
        Conflict: same id + different digest → C2ConflictError STOP.
        """
        if producer_event_id in self._entries:
            existing = self._entries[producer_event_id]
            if existing.envelope_sha256 != envelope_sha256:
                raise C2ConflictError(
                    f"CONFLICT: producer_event_id={producer_event_id!r} was previously "
                    f"journaled with digest={existing.envelope_sha256!r} but now "
                    f"computes {envelope_sha256!r}. STOP."
                )
            # Same id + same digest → idempotent NO-OP
            return existing

        entry = ConsumerJournalEntry(
            producer_event_id=producer_event_id,
            opportunity_id=opportunity_id,
            envelope_sha256=envelope_sha256,
            state="PENDING",
        )
        self._append_and_fsync(entry)
        self._entries[producer_event_id] = entry
        return entry

    def transition_applied(self, producer_event_id: str) -> None:
        """Transition PENDING → APPLIED after durable write + readback.

        Writes the APPLIED record to disk, fsyncs, then reads back to verify.
        Only sets in-memory state to APPLIED after successful readback.
        """
        entry = self._entries.get(producer_event_id)
        if entry is None:
            raise C2ConflictError(
                f"APPLIED_UNKNOWN_ID: {producer_event_id!r} not in journal"
            )
        if entry.state != "PENDING":
            # Already APPLIED or ACKED — idempotent
            return

        entry.state = "APPLIED"
        self._append_and_fsync(entry)

        # Readback verification: confirm the last APPLIED record is on disk
        disk_entries = _load_journal_file(self._path)
        disk_entry = disk_entries.get(producer_event_id)
        if disk_entry is None or disk_entry.state not in ("APPLIED", "ACKED"):
            # Readback failed — revert in-memory state
            entry.state = "PENDING"
            raise C2ConflictError(
                f"APPLIED_READBACK_FAILED: {producer_event_id!r} not found "
                f"as APPLIED on disk after write+fsync"
            )

    def transition_acked(self, producer_event_ids: list[str]) -> int:
        """Transition APPLIED → ACKED for confirmed producer_event_ids."""
        acked = 0
        for pid in producer_event_ids:
            entry = self._entries.get(pid)
            if entry is None:
                raise C2ConflictError(f"ACK_UNKNOWN_ID: {pid!r} not in journal")
            if entry.state == "PENDING":
                raise C2ConflictError(
                    f"ACK_NOT_APPLIED: {pid!r} still in PENDING state"
                )
            if entry.state == "APPLIED":
                entry.state = "ACKED"
                self._append_and_fsync(entry)
                acked += 1
        return acked

    def _append_and_fsync(self, entry: ConsumerJournalEntry) -> None:
        """Append one JSON-line record to the journal file and fsync."""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        record = {
            "envelope_sha256": entry.envelope_sha256,
            "opportunity_id": entry.opportunity_id,
            "producer_event_id": entry.producer_event_id,
            "state": entry.state,
        }
        line = json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n"
        with open(self._path, "ab") as fh:
            fh.write(line.encode("utf-8"))
            fh.flush()
            os.fsync(fh.fileno())


def _load_journal_file(path: Path) -> dict[str, ConsumerJournalEntry]:
    """Load and reconcile journal from JSON-lines file.

    State may only PROGRESS (PENDING → APPLIED → ACKED) for a given
    producer_event_id.  If the same pid appears with a DIFFERENT envelope_sha256
    the journal has been tampered — STOP immediately with C2ConflictError.
    """
    entries: dict[str, ConsumerJournalEntry] = {}
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
                pid = rec["producer_event_id"]
                if pid in entries:
                    existing = entries[pid]
                    # STOP on digest inconsistency — same pid, different sha256
                    # indicates history overwrite attempt or data corruption
                    if existing.envelope_sha256 != rec["envelope_sha256"]:
                        raise C2ConflictError(
                            f"JOURNAL_DIGEST_INCONSISTENCY: pid={pid!r} "
                            f"stored={existing.envelope_sha256!r} "
                            f"new={rec['envelope_sha256']!r}"
                        )
                    # Same digest: state can only progress; ignore regression
                    state_order = {"PENDING": 0, "APPLIED": 1, "ACKED": 2}
                    if state_order.get(rec["state"], -1) >= state_order.get(existing.state, -1):
                        entries[pid] = ConsumerJournalEntry(
                            producer_event_id=pid,
                            opportunity_id=rec["opportunity_id"],
                            envelope_sha256=rec["envelope_sha256"],
                            state=rec["state"],
                        )
                else:
                    entries[pid] = ConsumerJournalEntry(
                        producer_event_id=pid,
                        opportunity_id=rec["opportunity_id"],
                        envelope_sha256=rec["envelope_sha256"],
                        state=rec["state"],
                    )
            except (json.JSONDecodeError, KeyError):
                # Corrupted line — skip (partial write at crash boundary)
                continue
    return entries


def load_journal(path: Path | str) -> "DurableJournal":
    """Load an existing journal from disk for new-process restart.

    Returns a DurableJournal with all prior entries reconciled.
    If the file does not exist, returns an empty journal.
    """
    j = DurableJournal.__new__(DurableJournal)
    j._path = Path(path)
    j._entries = {}
    if j._path.exists():
        j._entries = _load_journal_file(j._path)
    return j


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _strategy_digest(strategy_id: str, strategy_version: str, policy_id: str) -> str:
    payload = {"policy_id": policy_id, "strategy_id": strategy_id,
               "strategy_version": strategy_version}
    return _sha256_hex(_canonical_bytes(payload))


def _assumptions_digest(source_lag_ms: int, latency_ms: int) -> str:
    payload = {"latency_assumption_ms": latency_ms, "source_lag_assumption_ms": source_lag_ms}
    return _sha256_hex(_canonical_bytes(payload))


def _opportunity_id(trial_id: str, strategy_instance_id: str,
                    decision_cutoff_ms: int, dataset_version: int) -> str:
    """Deterministic per spec: sha256(canonical([trial_id, strategy_instance_id,
    decision_cutoff_ms, dataset_version]))."""
    return _sha256_hex(_canonical_bytes(
        [trial_id, strategy_instance_id, decision_cutoff_ms, dataset_version]
    ))


def _producer_event_id(run_manifest_sha256: str, opportunity_id: str,
                       prefix_bar_checksums_sha256: str) -> str:
    """Deterministic per spec: sha256(canonical([run_manifest_sha256, opportunity_id,
    prefix_bar_checksums_sha256]))."""
    return _sha256_hex(_canonical_bytes(
        [run_manifest_sha256, opportunity_id, prefix_bar_checksums_sha256]
    ))


def _prefix_checksums_sha256(bars_in_prefix: list[P0Bar]) -> str:
    """sha256(canonical(ordered [bar_checksum]))."""
    return _sha256_hex(_canonical_bytes([b.bar_checksum for b in bars_in_prefix]))


def _envelope_sha256(envelope_dict: dict[str, Any]) -> str:
    """Compute hash over envelope dict excluding its own envelope_sha256 field."""
    payload = {k: v for k, v in envelope_dict.items() if k != "envelope_sha256"}
    return _sha256_hex(_canonical_bytes(payload))


# ---------------------------------------------------------------------------
# Run manifest SHA (C2 produces from C1 manifest)
# ---------------------------------------------------------------------------

def _run_manifest_sha256(manifest: P0SourceManifest, trial_id: str,
                          strategy_id: str, strategy_version: str,
                          strategy_digest: str, policy_id: str,
                          policy_digest: str, assumptions_digest: str) -> str:
    """SHA-256 over the canonical run manifest (excluding its own sha256 field)."""
    run_manifest = {
        "account_id": f"{trial_id}-ACCOUNT",
        "assumptions_digest": assumptions_digest,
        "correction_lineage_sha256": manifest.correction_lineage_sha256,
        "custody_status": manifest.custody_status,
        "dataset_id": manifest.dataset_id,
        "dataset_version": manifest.dataset_version,
        "exchange": manifest.exchange,
        "gap_inventory_sha256": manifest.gap_inventory_sha256,
        "interval_ms": manifest.interval_ms,
        "manifest_integrity_sha256": manifest.manifest_integrity_sha256,
        "market": manifest.market,
        "mode": manifest.mode,
        "ordered_bar_checksums_sha256": manifest.ordered_bar_checksums_sha256,
        "policy_digest": policy_digest,
        "policy_id": policy_id,
        "project_id": manifest.project_id,
        "raw_generation_id": manifest.raw_generation_id,
        "receipt_missing_reason": manifest.receipt_missing_reason,
        "receipt_status": manifest.receipt_status,
        "research_only": manifest.research_only,
        "schema": manifest.schema,
        "source_bytes_sha256": manifest.source_bytes_sha256,
        "source_provider": manifest.source_provider,
        "source_receipt_sha256": manifest.source_receipt_sha256,
        "source_version": manifest.source_version,
        "strategy_digest": strategy_digest,
        "strategy_id": strategy_id,
        "strategy_version": strategy_version,
        "symbol": manifest.symbol,
        "timezone": manifest.timezone,
        "trial_id": trial_id,
        "window_end_exclusive_ms": manifest.window_end_exclusive_ms,
        "window_start_ms": manifest.window_start_ms,
    }
    return _sha256_hex(_canonical_bytes(run_manifest))


# ---------------------------------------------------------------------------
# Decision production
# ---------------------------------------------------------------------------

def produce_envelopes(
    manifest: P0SourceManifest,
    *,
    trial_id: str,
    journal_path: Path | str,
) -> list[DecisionEnvelope]:
    """Produce all scheduled decision envelopes from a validated C1 manifest.

    Each 15m bar whose index >= MIN_PREFIX_BARS receives a decision envelope,
    using ONLY bars strictly before decision_cutoff_ms (no lookahead).

    Parameters
    ----------
    manifest:
        Validated P0SourceManifest from C1.
    trial_id:
        Frozen trial identifier (e.g. "P0-DEV-BTCUSDT-15M-2024-01-01").
    journal_path:
        Path to the durable JSON-lines journal file.
        Created on first run; loaded for idempotent restart.
        Same key + same digest = NO-OP (idempotent).
        Same key + different digest = C2ConflictError STOP.

    Returns
    -------
    list[DecisionEnvelope]
        One per scheduled decision. BLOCKED envelopes included (full denominator).
    """
    journal = load_journal(journal_path)

    # --- Frozen identity artifacts ---
    strat_digest = _strategy_digest(STRATEGY_ID, STRATEGY_VERSION, POLICY_ID)
    policy_digest = _sha256_hex(_canonical_bytes(
        {"policy_id": POLICY_ID, "strategy_id": STRATEGY_ID}
    ))
    assumptions_digest = _assumptions_digest(SOURCE_LAG_ASSUMPTION_MS, LATENCY_ASSUMPTION_MS)
    strategy_instance_id = _sha256_hex(_canonical_bytes(
        {"dataset_id": manifest.dataset_id, "policy_id": POLICY_ID,
         "strategy_id": STRATEGY_ID, "trial_id": trial_id}
    ))
    account_id = f"{trial_id}-ACCOUNT"

    run_manifest_sha = _run_manifest_sha256(
        manifest, trial_id, STRATEGY_ID, STRATEGY_VERSION,
        strat_digest, POLICY_ID, policy_digest, assumptions_digest
    )

    bars = manifest.bars
    envelopes: list[DecisionEnvelope] = []

    # Decision points: for each bar at index i >= MIN_PREFIX_BARS,
    # the prefix is bars[0..i-1] (i bars), cutoff = bars[i-1].bar_close_ms + 1
    # Decision ms = cutoff + SOURCE_LAG_ASSUMPTION_MS + LATENCY_ASSUMPTION_MS
    # (modeled evaluation instant, not an observed timestamp)

    for i in range(MIN_PREFIX_BARS, len(bars) + 1):
        # The decision considers bars[0..i-1] as the available prefix.
        # The "evaluation bar" is bars[i-1] (last completed bar in prefix).
        # Next bar (if any) is bars[i] — never included in prefix.
        prefix_bars = list(bars[:i])
        last_bar = prefix_bars[-1]

        decision_cutoff_ms = last_bar.bar_close_ms + 1  # strictly after last complete bar
        decision_ms = (
            decision_cutoff_ms + SOURCE_LAG_ASSUMPTION_MS + LATENCY_ASSUMPTION_MS
        )

        prefix_sha = _prefix_checksums_sha256(prefix_bars)
        opp_id = _opportunity_id(
            trial_id, strategy_instance_id, decision_cutoff_ms, manifest.dataset_version
        )
        prod_event_id = _producer_event_id(run_manifest_sha, opp_id, prefix_sha)

        # Determine disposition: EVALUABLE if prefix complete and no gaps
        has_gaps = any(b.gap_state != "COMPLETE" for b in prefix_bars)
        if has_gaps or len(prefix_bars) < MIN_PREFIX_BARS:
            disposition = "BLOCKED"
            reason_code = "INCOMPLETE_PREFIX"
        else:
            disposition = "EVALUABLE_RETROSPECTIVE"
            reason_code = None

        # Build envelope dict for hashing
        env_dict: dict[str, Any] = {
            "account_id": account_id,
            "availability_mode": "RETROSPECTIVE_NON_PIT",
            "correction_lineage_sha256": manifest.correction_lineage_sha256,
            "coverage_status": "COMPLETE" if not has_gaps else "INCOMPLETE",
            "dataset_id": manifest.dataset_id,
            "dataset_version": manifest.dataset_version,
            "decision_cutoff_ms": decision_cutoff_ms,
            "decision_ms": decision_ms,
            "feature_policy_version": "BASE-20-10-v1",
            "gap_inventory_sha256": manifest.gap_inventory_sha256,
            "input_disposition": disposition,
            "latency_assumption_ms": LATENCY_ASSUMPTION_MS,
            "opportunity_id": opp_id,
            "prefix_bar_checksums_sha256": prefix_sha,
            "prefix_end_exclusive_ms": decision_cutoff_ms,
            "prefix_start_ms": bars[0].bar_open_ms,
            "producer_event_id": prod_event_id,
            "reason_code": reason_code,
            "run_manifest_sha256": run_manifest_sha,
            "schema": SCHEMA,
            "source_lag_assumption_ms": SOURCE_LAG_ASSUMPTION_MS,
            "strategy_digest": strat_digest,
            "strategy_id": STRATEGY_ID,
            "strategy_instance_id": strategy_instance_id,
            "strategy_version": STRATEGY_VERSION,
            "trial_id": trial_id,
        }
        env_sha = _envelope_sha256(env_dict)

        # --- Durable journal: PENDING write (idempotent; conflict raises C2ConflictError) ---
        journal.write_pending(
            producer_event_id=prod_event_id,
            opportunity_id=opp_id,
            envelope_sha256=env_sha,
        )

        envelope = DecisionEnvelope(
            schema=SCHEMA,
            trial_id=trial_id,
            run_manifest_sha256=run_manifest_sha,
            dataset_id=manifest.dataset_id,
            dataset_version=manifest.dataset_version,
            strategy_id=STRATEGY_ID,
            strategy_version=STRATEGY_VERSION,
            strategy_digest=strat_digest,
            strategy_instance_id=strategy_instance_id,
            account_id=account_id,
            opportunity_id=opp_id,
            decision_ms=decision_ms,
            decision_cutoff_ms=decision_cutoff_ms,
            prefix_start_ms=bars[0].bar_open_ms,
            prefix_end_exclusive_ms=decision_cutoff_ms,
            prefix_bar_checksums_sha256=prefix_sha,
            feature_policy_version="BASE-20-10-v1",
            gap_inventory_sha256=manifest.gap_inventory_sha256,
            correction_lineage_sha256=manifest.correction_lineage_sha256,
            coverage_status="COMPLETE" if not has_gaps else "INCOMPLETE",
            availability_mode="RETROSPECTIVE_NON_PIT",
            source_lag_assumption_ms=SOURCE_LAG_ASSUMPTION_MS,
            latency_assumption_ms=LATENCY_ASSUMPTION_MS,
            producer_event_id=prod_event_id,
            input_disposition=disposition,
            reason_code=reason_code,
            envelope_sha256=env_sha,
        )
        envelopes.append(envelope)

        # Transition PENDING → APPLIED: durable write + fsync + readback verification
        # Only sets in-memory state to APPLIED after confirmed readback.
        journal.transition_applied(prod_event_id)

    return envelopes


def ack_envelopes(
    producer_event_ids: list[str],
    journal: "DurableJournal",
) -> int:
    """Transition APPLIED → ACKED for all confirmed producer_event_ids.

    Called by the downstream consumer (F1/Factory) after confirming it has
    successfully consumed and stored the envelopes. This completes the
    PENDING→APPLIED→ACKED lifecycle.

    Parameters
    ----------
    producer_event_ids:
        IDs to acknowledge. Must already be APPLIED in the journal.
    journal:
        The DurableJournal instance (writes ACKED state to disk + fsync).

    Returns
    -------
    int
        Number of entries transitioned to ACKED.
    """
    return journal.transition_acked(producer_event_ids)
