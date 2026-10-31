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
    """Durable consumer journal record (PENDING→APPLIED→ACKED).

    consumer_receipt_hash:
        SHA-256 or equivalent receipt proof from the downstream consumer (F1/Factory)
        confirming it has durably stored the envelope.  Set when transition_acked()
        is called with consumer_receipts; None when no downstream receipt was supplied.
        An absent receipt MUST prevent ACKED.
    """
    producer_event_id: str
    opportunity_id: str
    envelope_sha256: str
    state: str    # "PENDING" | "APPLIED" | "ACKED"
    consumer_receipt_hash: str | None = None
    source_bytes_sha256: str | None = None
    run_manifest_sha256: str | None = None
    trial_id: str | None = None
    strategy_digest: str | None = None
    policy_id: str | None = None
    assumptions_digest: str | None = None


def _verify_factory_receipt(path: Path, entry: ConsumerJournalEntry) -> str:
    """Validate Factory's agreed durable per-decision receipt (Issue #180/6542255718).

    Receipt format: aql.p0.factory-consumer-effect-receipt.v1, canonical
    sha256 commitments for per-decision effect and entire receipt. Optional
    financial events MUST be read from the actual Factory receipt journal in
    the SAME directory as the decision receipt (financial_receipts.jsonl).
    The Factory writer must fsync and read back both stores before acknowledging.
    """
    required_entry = (
        "source_bytes_sha256", "run_manifest_sha256", "trial_id",
        "strategy_digest", "policy_id", "assumptions_digest",
    )
    if any(not getattr(entry, key) for key in required_entry):
        raise C2ConflictError("ACK_PRODUCER_BINDING_INCOMPLETE")
    try:
        raw = path.read_bytes()
        doc = json.loads(raw)
        if not isinstance(doc, dict) or doc.get("schema") != "aql.p0.factory-consumer-effect-receipt.v1":
            raise C2ConflictError("ACK_FACTORY_RECEIPT_SCHEMA_MISMATCH")
        identity = {
            "producer_event_id": entry.producer_event_id,
            "opportunity_id": entry.opportunity_id,
            "envelope_sha256": entry.envelope_sha256,
            "run_manifest_sha256": entry.run_manifest_sha256,
            "trial_id": entry.trial_id,
            "strategy_digest": entry.strategy_digest,
            "policy_id": entry.policy_id,
            "assumptions_digest": entry.assumptions_digest,
        }
        if any(doc.get(k) != v for k, v in identity.items()):
            raise C2ConflictError("ACK_FACTORY_RECEIPT_BINDING_MISMATCH")
        disposition = doc.get("effect_disposition")
        event_ids = doc.get("ordered_financial_event_ids")
        payload_hashes = doc.get("ordered_financial_payload_hashes")
        if (not isinstance(disposition, str) or not disposition or
            not isinstance(event_ids, list) or not isinstance(payload_hashes, list) or
            len(event_ids) != len(payload_hashes) or len(set(event_ids)) != len(event_ids) or
            any(not isinstance(v, str) or not v for v in event_ids) or
            any(not isinstance(v, str) or len(v) != 64 for v in payload_hashes)):
            raise C2ConflictError("ACK_FACTORY_EFFECT_IDENTITY_INVALID")
        effect = {
            "producer_event_id": entry.producer_event_id,
            "envelope_sha256": entry.envelope_sha256,
            "run_manifest_sha256": entry.run_manifest_sha256,
            "opportunity_id": entry.opportunity_id,
            "effect_disposition": disposition,
            "ordered_financial_event_ids": event_ids,
            "ordered_financial_payload_hashes": payload_hashes,
        }
        effect_sha = _sha256_hex(_canonical_bytes(effect))
        if doc.get("consumer_effect_digest") != effect_sha:
            raise C2ConflictError("ACK_FACTORY_EFFECT_DIGEST_MISMATCH")
        receipt_payload = {k: v for k, v in doc.items() if k != "receipt_sha256"}
        if doc.get("receipt_sha256") != _sha256_hex(_canonical_bytes(receipt_payload)):
            raise C2ConflictError("ACK_FACTORY_RECEIPT_SHA256_MISMATCH")
        # Verify financial event payloads by reading the REAL persisted journal,
        # not trusting a supplied list of hashes. For NO_SIGNAL/NO_FILL etc.,
        # an empty event list is permitted but durable decision receipt required.
        if event_ids:
            financial_path = path.parent / "financial_receipts.jsonl"
            persisted = {}
            for line in financial_path.read_bytes().splitlines():
                if not line.strip():
                    continue
                event_rec = json.loads(line)
                event_id = event_rec["event_id"]
                payload_hash = event_rec["payload_hash"]
                recomputed = _sha256_hex(_canonical_bytes(
                    {k: v for k, v in event_rec.items() if k != "payload_hash"}
                ))
                if payload_hash != recomputed:
                    raise C2ConflictError("ACK_FINANCIAL_EVENT_PAYLOAD_TAMPER")
                if event_id in persisted and persisted[event_id] != payload_hash:
                    raise C2ConflictError("ACK_FINANCIAL_EVENT_ID_CONFLICT")
                persisted[event_id] = payload_hash
            for event_id, payload_hash in zip(event_ids, payload_hashes):
                if persisted.get(event_id) != payload_hash:
                    raise C2ConflictError("ACK_FINANCIAL_EVENT_NOT_DURABLE")
        return _sha256_hex(raw)
    except C2ConflictError:
        raise
    except (OSError, ValueError, TypeError, AttributeError, KeyError) as exc:
        raise C2ConflictError("ACK_FACTORY_RECEIPT_READBACK_INVALID") from exc


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
        source_bytes_sha256: str | None = None,
        run_manifest_sha256: str | None = None,
        trial_id: str | None = None,
        strategy_digest: str | None = None,
        policy_id: str | None = None,
        assumptions_digest: str | None = None,
    ) -> ConsumerJournalEntry:
        """Append PENDING entry to disk + fsync. Returns the entry.

        Idempotent: same id + same digest → returns existing entry unchanged.
        Conflict: same id + different digest → C2ConflictError STOP.
        """
        if producer_event_id in self._entries:
            existing = self._entries[producer_event_id]
            if (existing.envelope_sha256 != envelope_sha256 or (source_bytes_sha256 is not None and existing.source_bytes_sha256 not in (None, source_bytes_sha256)) or (run_manifest_sha256 is not None and existing.run_manifest_sha256 not in (None, run_manifest_sha256))):
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
            source_bytes_sha256=source_bytes_sha256,
            run_manifest_sha256=run_manifest_sha256,
            trial_id=trial_id,
            strategy_digest=strategy_digest,
            policy_id=policy_id,
            assumptions_digest=assumptions_digest,
        )
        self._append_and_fsync(entry)
        self._entries[producer_event_id] = entry
        return entry

    def transition_applied(self, producer_event_id: str) -> None:
        """Transition PENDING → APPLIED after durable write + readback.

        Writes the APPLIED record to disk, fsyncs, then reads back to verify.
        Only sets in-memory state to APPLIED after successful readback.

        ACK SEMANTICS WARNING — APPLIED ≠ downstream confirmed:
          APPLIED means only that this producer durably wrote the entry and
          verified the write via readback (fsync + re-read).  It does NOT
          mean the downstream consumer (F1/Factory) has received, processed,
          or durably stored the envelope.  Downstream confirmation is recorded
          separately via transition_acked() with a consumer_receipt_hash.
        """
        entry = self._entries.get(producer_event_id)
        if entry is None:
            raise C2ConflictError(
                f"APPLIED_UNKNOWN_ID: {producer_event_id!r} not in journal"
            )
        if entry.state != "PENDING":
            # Already APPLIED or ACKED — idempotent
            return

        applied_entry = ConsumerJournalEntry(
            producer_event_id=entry.producer_event_id,
            opportunity_id=entry.opportunity_id,
            envelope_sha256=entry.envelope_sha256,
            state="APPLIED",
            consumer_receipt_hash=entry.consumer_receipt_hash,
            source_bytes_sha256=entry.source_bytes_sha256,
            run_manifest_sha256=entry.run_manifest_sha256,
        )
        self._append_and_fsync(applied_entry)

        # Readback verification: confirm the last APPLIED record is on disk
        disk_entries = _load_journal_file(self._path)
        disk_entry = disk_entries.get(producer_event_id)
        if disk_entry is None or disk_entry.state not in ("APPLIED", "ACKED"):
            # In-memory state was never promoted before the persisted readback.
            raise C2ConflictError(
                f"APPLIED_READBACK_FAILED: {producer_event_id!r} not found "
                f"as APPLIED on disk after write+fsync"
            )
        self._entries[producer_event_id] = applied_entry

    def transition_acked(self, producer_event_ids: list[str], consumer_receipts: dict[str, str] | None = None) -> int:
        """Accept only a persisted Factory receipt AND its matching persisted effect.

        Values in consumer_receipts are JSON receipt FILE PATHS, never naked hash
        strings. Factory must fsync the effect and receipt before passing path.
        Core re-reads both and verifies source/run/envelope/event binding.
        """
        if not consumer_receipts:
            raise C2ConflictError("ACK_CONSUMER_RECEIPT_REQUIRED")
        if len(set(producer_event_ids)) != len(producer_event_ids):
            raise C2ConflictError("ACK_DUPLICATE_EVENT_ID")
        validated = []
        for pid in producer_event_ids:
            entry = self._entries.get(pid)
            if entry is None:
                raise C2ConflictError(f"ACK_UNKNOWN_ID: {pid!r}")
            if entry.state == "PENDING":
                raise C2ConflictError(f"ACK_NOT_APPLIED: {pid!r}")
            receipt_path = consumer_receipts.get(pid)
            if not isinstance(receipt_path, str) or not receipt_path:
                raise C2ConflictError(f"ACK_CONSUMER_RECEIPT_REQUIRED: {pid!r}")
            verified_sha = _verify_factory_receipt(Path(receipt_path), entry)
            if entry.state == "ACKED":
                if entry.consumer_receipt_hash != verified_sha:
                    raise C2ConflictError(f"ACK_RECEIPT_CONFLICT: {pid!r}")
                continue
            validated.append((entry, verified_sha))
        for entry, digest in validated:
            new_entry = ConsumerJournalEntry(
                producer_event_id=entry.producer_event_id,
                opportunity_id=entry.opportunity_id,
                envelope_sha256=entry.envelope_sha256,
                state="ACKED",
                consumer_receipt_hash=digest,
                source_bytes_sha256=entry.source_bytes_sha256,
                run_manifest_sha256=entry.run_manifest_sha256,
                trial_id=entry.trial_id,
                strategy_digest=entry.strategy_digest,
                policy_id=entry.policy_id,
                assumptions_digest=entry.assumptions_digest,
            )
            self._append_and_fsync(new_entry)
            readback = _load_journal_file(self._path).get(entry.producer_event_id)
            if readback is None or readback.state != "ACKED" or readback.consumer_receipt_hash != digest:
                raise C2ConflictError(f"ACK_DISK_READBACK_FAILED: {entry.producer_event_id!r}")
            self._entries[entry.producer_event_id] = new_entry
        return len(validated)

    def _append_and_fsync(self, entry: ConsumerJournalEntry) -> None:
        """Append one JSON-line record to the journal file and fsync."""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        record: dict = {
            "envelope_sha256": entry.envelope_sha256,
            "opportunity_id": entry.opportunity_id,
            "producer_event_id": entry.producer_event_id,
            "state": entry.state,
        }
        if entry.consumer_receipt_hash is not None:
            record["consumer_receipt_hash"] = entry.consumer_receipt_hash
        if entry.source_bytes_sha256 is not None:
            record["source_bytes_sha256"] = entry.source_bytes_sha256
        if entry.run_manifest_sha256 is not None:
            record["run_manifest_sha256"] = entry.run_manifest_sha256
        for k in ("trial_id", "strategy_digest", "policy_id", "assumptions_digest"):
            if getattr(entry, k) is not None:
                record[k] = getattr(entry, k)
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

    TAIL-ONLY RECOVERY RULE:
      Only the LAST non-empty line in the file may be silently skipped on a
      parse error (truncated write at crash boundary).  Any corrupt line that
      is NOT the last non-empty line indicates mid-file corruption — STOP with
      C2ConflictError.  Silent skip of a mid-file corrupt line would hide data
      loss and is not recoverable.
    """
    entries: dict[str, ConsumerJournalEntry] = {}
    with open(path, "r", encoding="utf-8") as fh:
        raw_lines = fh.readlines()

    # Find index of last non-empty line (for tail-only recovery)
    last_nonempty_idx = -1
    for i, raw in enumerate(raw_lines):
        if raw.strip():
            last_nonempty_idx = i

    for line_no, raw in enumerate(raw_lines):
        line = raw.strip()
        if not line:
            continue
        is_tail = (line_no == last_nonempty_idx)
        try:
            rec = json.loads(line)
            pid = rec["producer_event_id"]
            if pid in entries:
                existing = entries[pid]
                # STOP on digest inconsistency — same pid, different sha256
                # indicates history overwrite attempt or data corruption
                if (existing.envelope_sha256 != rec["envelope_sha256"] or
                    existing.opportunity_id != rec["opportunity_id"] or
                    existing.source_bytes_sha256 != rec.get("source_bytes_sha256") or
                    existing.run_manifest_sha256 != rec.get("run_manifest_sha256") or
                    any(getattr(existing, key) != rec.get(key) for key in
                        ("trial_id", "strategy_digest", "policy_id", "assumptions_digest"))):
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
                        consumer_receipt_hash=rec.get("consumer_receipt_hash"),
                        source_bytes_sha256=rec.get("source_bytes_sha256"),
                        run_manifest_sha256=rec.get("run_manifest_sha256"),
                        trial_id=rec.get("trial_id"),
                        strategy_digest=rec.get("strategy_digest"),
                        policy_id=rec.get("policy_id"),
                        assumptions_digest=rec.get("assumptions_digest"),
                    )
            else:
                entries[pid] = ConsumerJournalEntry(
                    producer_event_id=pid,
                    opportunity_id=rec["opportunity_id"],
                    envelope_sha256=rec["envelope_sha256"],
                    state=rec["state"],
                    consumer_receipt_hash=rec.get("consumer_receipt_hash"),
                        source_bytes_sha256=rec.get("source_bytes_sha256"),
                        run_manifest_sha256=rec.get("run_manifest_sha256"),
                        trial_id=rec.get("trial_id"),
                        strategy_digest=rec.get("strategy_digest"),
                        policy_id=rec.get("policy_id"),
                        assumptions_digest=rec.get("assumptions_digest"),
                )
        except C2ConflictError:
            raise  # always re-raise digest conflict errors
        except (json.JSONDecodeError, KeyError):
            if is_tail:
                # Tail-only recovery: last line may be a partial write (crash) — skip
                continue
            raise C2ConflictError(
                f"JOURNAL_MID_FILE_CORRUPTION at line {line_no + 1}: "
                f"corrupt record before end of file — cannot safely recover. "
                f"Manual investigation required."
            )
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
            source_bytes_sha256=manifest.source_bytes_sha256,
            run_manifest_sha256=run_manifest_sha,
            trial_id=trial_id,
            strategy_digest=strat_digest,
            policy_id=POLICY_ID,
            assumptions_digest=assumptions_digest,
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
    *,
    consumer_receipts: dict[str, str] | None = None,
) -> int:
    """Transition APPLIED → ACKED for all confirmed producer_event_ids.

    Called by the downstream consumer (F1/Factory) after confirming it has
    successfully consumed and stored the envelopes. This completes the
    PENDING→APPLIED→ACKED lifecycle.

    ACK SEMANTICS: this records that the downstream consumer acknowledged
    receipt, but does NOT verify that the consumer has committed the data
    to its own durable store.  Callers SHOULD supply consumer_receipts
    (a hash or token from the downstream consumer's own storage receipt)
    whenever available so the journal carries end-to-end evidence.

    Parameters
    ----------
    producer_event_ids:
        IDs to acknowledge. Must already be APPLIED in the journal.
    journal:
        The DurableJournal instance (writes ACKED state to disk + fsync).
    consumer_receipts:
        Optional mapping of producer_event_id → downstream storage receipt hash.
        Written to the journal entry as consumer_receipt_hash for audit purposes.

    Returns
    -------
    int
        Number of entries transitioned to ACKED.
    """
    return journal.transition_acked(producer_event_ids, consumer_receipts=consumer_receipts)
