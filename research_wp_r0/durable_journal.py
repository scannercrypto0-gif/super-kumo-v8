"""WP-R7: single-writer local JSONL journal for trial-family and holdout events.

Fail closed: verify the *entire* chain and replay the logical state machine on
open. Never truncate/repair a torn tail automatically. A local SHA-256 chain is
TAMPER-EVIDENT only relative to an externally retained trustworthy anchor:
an attacker able to rewrite the full journal can recompute every hash.

Synthetic/offline only. No database, cloud provider, operator permission or
live-trader access. stdlib Python 3.10+.
"""
from __future__ import annotations

from datetime import datetime
import json
import os
from pathlib import Path
from typing import Any

from research_wp_r0.trial_holdout import (
    Attempt, AttemptState, FrozenSearchFamily, HoldoutEvent,
    TrialFamilyLedger, fingerprint, utc_stamp,
)


class JournalIntegrityError(ValueError):
    """Journal verification, schema or state-machine replay has failed."""


def _canonical(record: dict) -> bytes:
    return json.dumps(record, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False).encode("utf-8")


def _family_data(family: FrozenSearchFamily) -> dict[str, Any]:
    return {
        "family_id": family.family_id,
        "protocol_digest": family.protocol_digest,
        "temporal_manifest_digest": family.temporal_manifest_digest,
        "dataset_version": family.dataset_version,
        "metric_name": family.metric_name,
        "metric_direction": family.metric_direction,
        "candidate_ids": list(family.candidate_ids),
        "alpha": family.alpha,
        "declared_at": utc_stamp(family.declared_at),
    }


def _replay_event(ledger: TrialFamilyLedger, kind: str, data: dict) -> None:
    try:
        if kind == "ATTEMPT":
            if set(data) != {"candidate_id", "state", "result_digest", "recorded_at", "marginal_p_value"}:
                raise ValueError("Bad attempt schema")
            ledger.record_attempt(Attempt(
                candidate_id=data["candidate_id"],
                state=AttemptState(data["state"]),
                result_digest=data["result_digest"],
                recorded_at=datetime.fromisoformat(data["recorded_at"]),
                marginal_p_value=data["marginal_p_value"],
            ))
        elif kind == "SELECT":
            if set(data) != {"candidate_id", "at"}:
                raise ValueError("Bad selection schema")
            ledger.select(data["candidate_id"], at=datetime.fromisoformat(data["at"]))
        elif kind == "HOLDOUT":
            if set(data) != {"event_type", "at", "evidence_digest"}:
                raise ValueError("Bad holdout schema")
            ledger.holdout_event(HoldoutEvent(
                event_type=data["event_type"],
                at=datetime.fromisoformat(data["at"]),
                evidence_digest=data["evidence_digest"],
            ))
        else:
            raise ValueError("Unknown journal event")
    except (ValueError, TypeError, KeyError, AttributeError) as exc:
        raise JournalIntegrityError("Invalid replayed research event") from exc


class DurableTrialJournal:
    """Exclusive local writer, whose evidence must be externally anchored.

    close() is needed to release the exclusive writer lock. Do not forcibly
    remove an orphaned .lock until independently confirming no writer exists.
    """

    GENESIS = "0" * 64
    MAX_LINE = 1_000_000

    def __init__(self, path: str | Path, family: FrozenSearchFamily) -> None:
        self.path = Path(path)
        self.family = family
        self._lock_path = self.path.with_name(self.path.name + ".lock")
        self._lock_fd: int | None = None
        self._closed = False
        self._poisoned = False
        self._events: dict[str, bytes] = {}
        self._sequence = 0
        self._head = self.GENESIS
        self._ledger = TrialFamilyLedger(family)

        if not self.path.parent.is_dir():
            raise FileNotFoundError("Journal parent directory must exist")
        # Lock prevents cooperating processes using this implementation from
        # racing. It is NOT an OS-enforced universal lock against other tools.
        self._lock_fd = os.open(self._lock_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            if self.path.exists():
                self._restore()
            else:
                self._append("FAMILY", _family_data(family), "family:" + family.digest)
        except BaseException:
            self.close()
            raise

    def __enter__(self) -> "DurableTrialJournal":
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

    @property
    def head(self) -> str:
        return self._head

    @property
    def sequence(self) -> int:
        return self._sequence

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        if self._lock_fd is not None:
            os.close(self._lock_fd)
            self._lock_fd = None
            # Only the lock owned by this instance may be removed.
            self._lock_path.unlink()

    def report(self):
        self._require_healthy()
        return self._ledger.report()

    def _require_healthy(self) -> None:
        if self._closed or self._poisoned:
            raise JournalIntegrityError("Journal closed or write state uncertain")

    def _append(self, kind: str, data: dict, event_id: str) -> bool:
        self._require_healthy()
        if not event_id or not isinstance(event_id, str):
            raise ValueError("Stable event id required")
        payload = {"kind": kind, "data": data, "event_id": event_id}
        canonical_payload = _canonical(payload)
        prior = self._events.get(event_id)
        if prior is not None:
            if prior == canonical_payload:
                return False  # idempotent exactly-the-same committed event
            raise JournalIntegrityError("Conflicting duplicate event id")
        number = self._sequence + 1
        record = {"sequence": number, "prev_hash": self._head, **payload}
        record["hash"] = fingerprint(record)
        encoded = _canonical(record) + b"\n"
        if len(encoded) > self.MAX_LINE:
            raise ValueError("Oversized journal entry")
        # Exclusive lock acquired before inspection, no concurrent writers
        # under this contract. O_APPEND, fsync and write-all minimize torn
        # records but do not guarantee atomic multi-process appends.
        flags = os.O_WRONLY | os.O_CREAT | os.O_APPEND
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        try:
            fd = os.open(self.path, flags, 0o600)
            try:
                size = os.fstat(fd).st_size
                if self._sequence and size != self._persisted_size:
                    raise JournalIntegrityError("Journal changed outside active writer")
                if not self._sequence and size != 0:
                    raise JournalIntegrityError("New journal unexpectedly nonempty")
                written = 0
                while written < len(encoded):
                    amount = os.write(fd, encoded[written:])
                    if amount <= 0:
                        raise OSError("Non-progressing append")
                    written += amount
                os.fsync(fd)
            finally:
                os.close(fd)
        except BaseException:
            self._poisoned = True
            raise
        self._persisted_size = (getattr(self, "_persisted_size", 0) + len(encoded))
        self._sequence = number
        self._head = record["hash"]
        self._events[event_id] = canonical_payload
        return True

    def _restore(self) -> None:
        raw = self.path.read_bytes()
        if not raw or not raw.endswith(b"\n"):
            raise JournalIntegrityError("Empty or truncated journal (no automatic repair)")
        parts = raw.splitlines(keepends=True)
        if any(len(line) > self.MAX_LINE for line in parts):
            raise JournalIntegrityError("Oversized journal record")
        expected = self.GENESIS
        seen = {}
        reconstructed = TrialFamilyLedger(self.family)
        for idx, line in enumerate(parts, start=1):
            try:
                record = json.loads(line.decode("utf-8"))
                if not isinstance(record, dict) or _canonical(record) + b"\n" != line:
                    raise ValueError("Noncanonical JSON record")
                if set(record) != {"sequence", "prev_hash", "kind", "data", "event_id", "hash"}:
                    raise ValueError("Unexpected journal schema")
                if type(record["sequence"]) is not int or record["sequence"] != idx:
                    raise ValueError("Noncontiguous sequence")
                if record["prev_hash"] != expected:
                    raise ValueError("Broken predecessor hash")
                claim = record["hash"]
                without_hash = {k: v for k, v in record.items() if k != "hash"}
                if claim != fingerprint(without_hash):
                    raise ValueError("Tampered record hash")
                payload = {k: record[k] for k in ("kind", "data", "event_id")}
                if not isinstance(record["event_id"], str) or not record["event_id"]:
                    raise ValueError("Missing event identity")
                if record["event_id"] in seen:
                    raise ValueError("Duplicate event recorded on disk")
                if idx == 1:
                    if record["kind"] != "FAMILY" or record["data"] != _family_data(self.family):
                        raise ValueError("Frozen family mismatch")
                    if record["event_id"] != "family:" + self.family.digest:
                        raise ValueError("Frozen family identifier mismatch")
                else:
                    if record["kind"] == "FAMILY":
                        raise ValueError("Redefined trial family")
                    _replay_event(reconstructed, record["kind"], record["data"])
                seen[record["event_id"]] = _canonical(payload)
                expected = claim
            except (ValueError, TypeError, KeyError, UnicodeError, AttributeError) as exc:
                raise JournalIntegrityError(f"Invalid journal at record {idx}") from exc
        self._sequence = len(parts)
        self._head = expected
        self._events = seen
        self._ledger = reconstructed
        self._persisted_size = len(raw)

    def record_attempt(self, attempt: Attempt, *, event_id: str) -> None:
        self._require_healthy()
        data = {
            "candidate_id": attempt.candidate_id,
            "state": attempt.state.value,
            "result_digest": attempt.result_digest,
            "recorded_at": utc_stamp(attempt.recorded_at),
            "marginal_p_value": attempt.marginal_p_value,
        }
        self._validated_append("ATTEMPT", data, event_id)

    def select(self, candidate_id: str, *, at: datetime, event_id: str) -> None:
        self._validated_append("SELECT", {"candidate_id": candidate_id, "at": utc_stamp(at)}, event_id)

    def holdout_event(self, event: HoldoutEvent, *, event_id: str) -> None:
        self._validated_append("HOLDOUT", {
            "event_type": event.event_type, "at": utc_stamp(event.at),
            "evidence_digest": event.evidence_digest,
        }, event_id)

    def _validated_append(self, kind: str, data: dict, event_id: str) -> None:
        self._require_healthy()
        payload = _canonical({"kind": kind, "data": data, "event_id": event_id})
        if event_id in self._events:
            if self._events[event_id] == payload:
                return
            raise JournalIntegrityError("Conflicting duplicate event id")
        # Validate on a fresh state-machine reconstruction before writing. A
        # durable append is the commit point; never update in-memory state first.
        shadow = TrialFamilyLedger(self.family)
        for earlier in self.path.read_bytes().splitlines()[1:]:
            r = json.loads(earlier)
            _replay_event(shadow, r["kind"], r["data"])
        _replay_event(shadow, kind, data)
        changed = self._append(kind, data, event_id)
        if changed:
            self._ledger = shadow
