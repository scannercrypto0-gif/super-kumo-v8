"""Bounded OFFLINE retained source. Never perform retain/step on a G1 callback.

Reuses the position journal's cooperating-writer lease, not a hostile-filesystem
security boundary. No automatic repair, pruning, runtime wiring or scheduler.
"""
from dataclasses import asdict
import hashlib
import json
import os
from pathlib import Path
import threading
from uuid import UUID

from .position_journal import (DurablePositionJournal,
                               _exclusive_writer, _WRITER_MUTEX)
from .positions import PositionEvent


class SourceIntegrityError(ValueError):
    """Source/receipt is ambiguous: retain evidence and stop replay."""


class SourceFullError(ValueError):
    """Nothing accepted: caller must retain the input elsewhere."""


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def _digest(value):
    return hashlib.sha256(_canonical(value)).hexdigest()


class RetainedObservationSource:
    """One generation, at most 128 events (including ACKed), no eviction.

    Each step handles at most one sequence; memory/scan work is capped by the
    configured source and dedicated journal limits. FULL is explicit admission
    failure, not an ACK. Source retention and disk IO belong outside G1.
    """

    def __init__(self, path, journal_path, source_generation_id, *, max_events=32):
        UUID(source_generation_id)
        if type(max_events) is not int or not 1 <= max_events <= 128:
            raise ValueError("max_events must be an integer in [1,128]")
        self.path, self.journal_path = Path(path).resolve(), Path(journal_path).resolve()
        if self.path == self.journal_path or self.path.name == self.journal_path.name + ".writer.lock" or self.journal_path.name == self.path.name + ".writer.lock":
            raise ValueError("source and dedicated journal paths must be distinct")
        self.max_events = max_events
        self._lock = threading.Lock()
        self.header = dict(kind="header", version=1, generation=source_generation_id,
                           journal=str(self.journal_path), max_events=max_events)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._lock, _exclusive_writer(self.path):
            if not self.path.exists():
                if self.journal_path.exists() and self.journal_path.stat().st_size:
                    raise SourceIntegrityError("missing source with populated target; recover evidence")
                self._write(self.header, "0" * 64, create=True)
            self._load()
            self._sync_source()

    def _sync_source(self):
        # Revalidate and resync readable records after an ambiguous earlier sync.
        with self.path.open("r+b") as handle:
            os.fsync(handle.fileno())

    def _write(self, data, previous, *, create=False):
        row = dict(previous=previous, data=data)
        row["digest"] = _digest(row)
        encoded = _canonical(row) + b"\n"
        with self.path.open("xb" if create else "ab") as handle:
            if handle.write(encoded) != len(encoded):
                raise SourceIntegrityError("short source write")
            handle.flush()
            os.fsync(handle.fileno())

    def _journal(self):
        # A dedicated bounded target is required. Do not scan arbitrary history.
        if self.journal_path.exists() and self.journal_path.stat().st_size > self.max_events * 8192:
            raise SourceIntegrityError("dedicated target exceeds offline byte limit")
        journal = DurablePositionJournal(self.journal_path)
        if len(journal.ledger.events) > self.max_events:
            raise SourceIntegrityError("dedicated target exceeds offline event limit")
        return journal

    def _load(self):
        """Read bounded, chained records; no tail repair or missing-file recreation."""
        previous, events, cursor = "0" * 64, [], 0
        seen = set()
        with self.path.open("rb") as handle:
            for index in range(2 * self.max_events + 2):
                raw = handle.readline(8193)
                if not raw:
                    break
                if len(raw) > 8192 or not raw.endswith(b"\n"):
                    raise SourceIntegrityError("oversize or torn source record")
                try:
                    row = json.loads(raw)
                    data = row["data"]
                    if set(row) != {"previous", "data", "digest"} or row["previous"] != previous or row["digest"] != _digest(dict(previous=previous, data=data)) or _canonical(row) + b"\n" != raw:
                        raise SourceIntegrityError("noncanonical source or chain mismatch")
                    previous = row["digest"]
                    if index == 0:
                        if data != self.header:
                            raise SourceIntegrityError("source identity/configuration changed")
                    elif data.get("kind") == "event":
                        if set(data) != {"kind", "seq", "event", "payload_hash"} or type(data["seq"]) is not int or data["seq"] != len(events) + 1 or len(events) >= self.max_events:
                            raise SourceIntegrityError("source sequence/limit mismatch")
                        event = PositionEvent(**data["event"])
                        identity = (event.position_id, event.event_id)
                        if identity in seen or _digest(data["event"]) != data["payload_hash"]:
                            raise SourceIntegrityError("source identity/hash conflict")
                        seen.add(identity)
                        events.append(event)
                    elif data.get("kind") == "ack":
                        if set(data) != {"kind", "seq", "payload_hash"} or type(data["seq"]) is not int or data["seq"] != cursor + 1 or data["seq"] > len(events) or data["payload_hash"] != _digest(asdict(events[cursor])):
                            raise SourceIntegrityError("ambiguous or skipped ACK")
                        cursor += 1
                    else:
                        raise SourceIntegrityError("unknown source record")
                except (KeyError, TypeError, ValueError) as exc:
                    raise SourceIntegrityError("invalid retained source") from exc
            else:
                raise SourceIntegrityError("source exceeds bounded record count")
        if previous == "0" * 64:
            raise SourceIntegrityError("empty source")
        # A forged/stale ACK cannot silently skip an absent or conflicting event.
        with _WRITER_MUTEX, _exclusive_writer(self.journal_path):
            journal = self._journal()
            for event in events[:cursor]:
                if journal.ledger.events.get((event.position_id, event.event_id)) != event:
                    raise SourceIntegrityError("ACK prefix missing from target journal")
            if cursor:
                with self.journal_path.open("r+b") as handle:
                    os.fsync(handle.fileno())
        return events, cursor, previous

    def retain(self, event):
        """Durably admit before any offer; identical identity returns same sequence."""
        if not isinstance(event, PositionEvent) or len(_canonical(asdict(event))) > 4096:
            raise ValueError("expected bounded PositionEvent")
        with self._lock, _exclusive_writer(self.path):
            events, cursor, tail = self._load()
            for seq, prior in enumerate(events, 1):
                if (prior.position_id, prior.event_id) == (event.position_id, event.event_id):
                    if prior != event:
                        raise SourceIntegrityError("conflicting source identity")
                    self._sync_source()
                    return seq
            if len(events) >= self.max_events:
                raise SourceFullError("retention full; no eviction, input NOT accepted")
            seq = len(events) + 1
            self._write(dict(kind="event", seq=seq, event=asdict(event),
                             payload_hash=_digest(asdict(event))), tail)
            return seq

    def status(self):
        with self._lock, _exclusive_writer(self.path):
            events, cursor, _ = self._load()
            return dict(retained=len(events), acked=cursor, pending=len(events)-cursor,
                        capacity=self.max_events, generation=self.header["generation"])

    def step(self, worker):
        """Verify/ACK OR offer one event; invoke only in the independent lane.

        The fsync below establishes a receipt even after an earlier append
        crashed after write but before sync. In-memory worker state never ACKs.
        """
        if Path(worker.journal_path).resolve() != self.journal_path:
            raise SourceIntegrityError("worker target mismatch")
        with self._lock, _exclusive_writer(self.path):
            events, cursor, tail = self._load()
            self._sync_source()
            if cursor == len(events):
                return "drained"
            event = events[cursor]
            identity = (event.position_id, event.event_id)
            with _WRITER_MUTEX, _exclusive_writer(self.journal_path):
                journal = self._journal()
                receipt = journal.ledger.events.get(identity)
                if receipt is not None and receipt != event:
                    raise SourceIntegrityError("target payload conflicts with retained event")
                if receipt is not None:
                    with self.journal_path.open("r+b") as handle:
                        os.fsync(handle.fileno())
                    self._write(dict(kind="ack", seq=cursor+1,
                                     payload_hash=_digest(asdict(event))), tail)
                    return "acked"
            report = worker.snapshot()
            if report["errors"] or not report["worker_alive"]:
                return "blocked"
            if identity in report["unconfirmed_event_ids"] or not report["identities_exhaustive"]:
                return "pending"
            return "offered" if worker.submit(event) else "backpressure"

    def schedule(self, lane, worker):
        """Bounded RAM scheduling only; rejection retains all source evidence.

        Existing BackgroundLane supplies the independent execution context.
        Call retain() from an offline producer, NEVER from G1's callback.
        """
        return lane.submit(lambda stop: None if stop.is_set() else self.step(worker))
