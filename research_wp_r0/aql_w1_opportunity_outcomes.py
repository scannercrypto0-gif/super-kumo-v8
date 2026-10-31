"""W1 research-only opportunity outcomes. No paper/order/position imports.

Retrospective market excursions are NOT fills, PIT observations, or realized PnL.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, is_dataclass
from hashlib import sha256
import json
import math
import os
from pathlib import Path

BAR_MS = 900_000
HORIZONS = (14_400_000, 86_400_000, 259_200_000)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def digest(value):
    return sha256(canonical(value).encode("utf-8")).hexdigest()


class EvidenceError(ValueError):
    pass


@dataclass(frozen=True)
class RetrospectiveSnapshot:
    trial_id: str
    manifest_sha256: str
    opportunity_id: str
    producer_event_id: str
    envelope_sha256: str
    decision_cutoff_ms: int
    decision_ms: int
    signal_state: str
    reason_code: str | None
    direction: str | None
    eligibility: str
    eligibility_evidence: str | None
    context_digest: str
    evidence_class: str = "RETROSPECTIVE_NON_PIT"
    receipt_ms: None = None
    available_at_ms: None = None

    def __post_init__(self):
        if self.decision_cutoff_ms % BAR_MS or self.decision_ms < self.decision_cutoff_ms:
            raise EvidenceError("invalid cutoff/decision time")
        if self.eligibility not in ("YES", "NO", "NOT_ESTABLISHED"):
            raise EvidenceError("unknown eligibility")
        if self.eligibility == "YES" and not self.eligibility_evidence:
            raise EvidenceError("eligibility requires predecision evidence")
        if self.direction not in ("LONG", "SHORT", None):
            raise EvidenceError("invalid direction")
        if self.receipt_ms is not None or self.available_at_ms is not None:
            raise EvidenceError("retrospective PIT time cannot be invented")

    @property
    def opportunity_identity(self):
        return digest({"trial_id": self.trial_id, "opportunity_id": self.opportunity_id,
                       "producer_event_id": self.producer_event_id,
                       "envelope_sha256": self.envelope_sha256})

    @property
    def snapshot_id(self):
        return digest({"schema": 1, **asdict(self)})


def _source_row(value):
    """Read actual C2/F1 dataclasses or JSON dictionaries."""
    if isinstance(value, dict):
        return value
    if is_dataclass(value) and not isinstance(value, type):
        return asdict(value)
    raise EvidenceError("unsupported source row type")


def _source_context_digest(envelope, selection):
    """Digest only source/predecision lineage, never future market bars."""
    fields = ("envelope_sha256", "prefix_bar_checksums_sha256",
              "feature_policy_version", "gap_inventory_sha256",
              "correction_lineage_sha256")
    return digest({"envelope": {k: envelope[k] for k in fields},
                   "selection_prefix": selection["prefix_bar_checksums_sha256"]})


def reconcile(envelopes, selections):
    """Exact 1:1 immutable source join; no outcome-based eligibility inference."""
    envelopes = [_source_row(x) for x in envelopes]
    selections = [_source_row(x) for x in selections]
    if len(envelopes) != len(selections):
        raise EvidenceError("source/selection count mismatch")
    by_id = {}
    for row in selections:
        key = (row["trial_id"], row["opportunity_id"], row["producer_event_id"])
        if key in by_id:
            raise EvidenceError("duplicate selection")
        by_id[key] = row
    result = []
    seen = set()
    for e in envelopes:
        key = (e["trial_id"], e["opportunity_id"], e["producer_event_id"])
        if key in seen or key not in by_id:
            raise EvidenceError("duplicate or missing envelope/selection")
        seen.add(key)
        s = by_id[key]
        for field in ("decision_cutoff_ms", "decision_ms", "producer_event_id", "opportunity_id", "trial_id", "prefix_start_ms", "prefix_end_exclusive_ms", "prefix_bar_checksums_sha256", "input_disposition", "strategy_id", "dataset_version"):
            if e.get(field) != s.get(field):
                raise EvidenceError("conflicting source " + field)
        result.append(RetrospectiveSnapshot(
            trial_id=e["trial_id"], manifest_sha256=e["run_manifest_sha256"],
            opportunity_id=e["opportunity_id"], producer_event_id=e["producer_event_id"],
            envelope_sha256=e["envelope_sha256"], decision_cutoff_ms=e["decision_cutoff_ms"],
            decision_ms=e["decision_ms"], signal_state=getattr(s["signal_state"], "value", str(s["signal_state"])),
            reason_code=s.get("reason_code"), direction=s.get("direction"),
            eligibility=s.get("eligibility", "NOT_ESTABLISHED"),
            eligibility_evidence=s.get("eligibility_evidence"),
            context_digest=_source_context_digest(e, s),
        ))
    if len(seen) != len(by_id):
        raise EvidenceError("orphan selection")
    return tuple(result)


def market_outcome(snapshot, horizon_ms, bars, *, source_version, source_end_exclusive_ms,
                   archive_finalized=True, policy_version="W1-MARKET-v1",
                   correction_generation="original"):
    """bars are OHLC dicts with open_ms/open/high/low/close and finalized flag.

    OPEN(t) is a non-executable retrospective reference; the modeled decision
    may occur later. All H/15m finalized bars are required, no partial MFE.
    """
    if not source_version or not policy_version or not correction_generation:
        raise EvidenceError("missing source or policy version")
    if horizon_ms not in HORIZONS:
        raise EvidenceError("unsupported horizon")
    t = snapshot.decision_cutoff_ms
    due = t + horizon_ms
    key = {"opportunity_identity": snapshot.opportunity_identity,
           "snapshot_id": snapshot.snapshot_id, "horizon_ms": horizon_ms,
           "source_version": source_version, "policy_version": policy_version,
           "correction_generation": correction_generation}
    result = {"outcome_id": digest(key), "evaluation_version_id": digest(key),
              **key, "due_at_ms": due,
              "reference_kind": "OPEN_AT_CUTOFF_NON_EXECUTABLE",
              "execution_status": "NOT_OBSERVED", "order_resolution": "NOT_ASSESSED",
              "window_quality": "NOT_READY", "excursion_metrics_status": "NOT_EVALUATED",
              "mfe": None, "mae": None, "status": "PENDING", "reason": None}
    if source_end_exclusive_ms < due:
        result.update(status="MISSING_DATA" if archive_finalized else "PENDING",
                      reason="ARCHIVE_END_CENSORED" if archive_finalized else "AWAITING_SOURCE")
        return result
    index = {}
    for bar in bars:
        ts = bar["open_ms"]
        if t <= ts < due:
            if ts in index:
                result.update(status="UNKNOWN", reason="DUPLICATE_BAR")
                return result
            index[ts] = bar
    expected = range(t, due, BAR_MS)
    if len(index) != horizon_ms // BAR_MS or any(ts not in index for ts in expected):
        result.update(status="MISSING_DATA", reason="GAPPED_WINDOW")
        return result
    ordered = [index[ts] for ts in expected]
    if any(not b.get("finalized", False) for b in ordered):
        result.update(status="MISSING_DATA", reason="UNFINALIZED_BAR")
        return result
    try:
        for b in ordered:
            o, h, l, c = (float(b[k]) for k in ("open", "high", "low", "close"))
            if not all(map(math.isfinite, (o, h, l, c))) or l <= 0 or l > min(o, c) or h < max(o, c):
                raise ValueError()
        base = float(ordered[0]["open"])
        if base <= 0:
            raise ValueError()
    except (KeyError, ValueError, TypeError):
        result.update(status="UNKNOWN", reason="INVALID_OHLC")
        return result
    if snapshot.direction not in ("LONG", "SHORT"):
        result.update(status="UNKNOWN", reason="DIRECTION_NOT_ESTABLISHED")
        return result
    highs = [float(b["high"]) for b in ordered]
    lows = [float(b["low"]) for b in ordered]
    favorable = (max(highs) / base - 1) if snapshot.direction == "LONG" else (1 - min(lows) / base)
    adverse = (1 - min(lows) / base) if snapshot.direction == "LONG" else (max(highs) / base - 1)
    result.update(status="EVALUATED", reason=None, mfe=max(0.0, favorable), mae=max(0.0, adverse),
                  window_quality="COMPLETE_FINALIZED", excursion_metrics_status="EVALUATED",
                  order_resolution="NOT_APPLICABLE", bar_count=len(ordered),
                  reference_price=base)
    return result


class AppendOnlyOutcomeJournal:
    """Research-only immutable outcomes, serialized and replay-validated.

    A lock directory is acquired atomically before re-reading and appending.
    Contention and crash-left locks fail closed; no automatic lock stealing.
    """

    def __init__(self, path):
        self.path = Path(path)
        self.lock_path = Path(str(self.path) + ".lock")
        self._seen = {}
        self._reload()

    def _reload(self):
        seen = {}
        if self.path.exists():
            with self.path.open("rb") as f:
                for line in f:
                    try:
                        record = json.loads(line)
                        payload = record["payload"]
                        if record["sha256"] != digest(payload):
                            raise EvidenceError("journal checksum mismatch")
                        key = payload["outcome_id"]
                        if payload.get("evaluation_version_id", key) != key:
                            raise EvidenceError("evaluation identity mismatch")
                        if payload.get("evaluation_record_id") != digest(
                                {k: v for k, v in payload.items() if k != "evaluation_record_id"}):
                            raise EvidenceError("evaluation record checksum mismatch")
                        encoded = canonical(payload)
                        if key in seen and seen[key] != encoded:
                            raise EvidenceError("conflicting outcome generation")
                        seen[key] = encoded
                    except (ValueError, KeyError, TypeError) as exc:
                        raise EvidenceError("corrupt journal; fail closed") from exc
        self._seen = seen

    def append(self, payload):
        payload = dict(payload)
        payload.setdefault("evaluation_record_id", digest(payload))
        key = payload["outcome_id"]
        if payload.get("evaluation_version_id", key) != key:
            raise EvidenceError("evaluation identity mismatch")
        if payload["evaluation_record_id"] != digest(
                {k: v for k, v in payload.items() if k != "evaluation_record_id"}):
            raise EvidenceError("evaluation record checksum mismatch")
        encoded = canonical(payload)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        try:
            self.lock_path.mkdir()
        except FileExistsError as exc:
            raise EvidenceError("outcome journal locked; fail closed") from exc
        try:
            self._reload()
            if key in self._seen:
                if self._seen[key] != encoded:
                    raise EvidenceError("conflicting outcome generation")
                return False
            record = (canonical({"payload": payload, "sha256": digest(payload)}) + "\n").encode()
            with self.path.open("ab") as f:
                f.write(record)
                f.flush()
                os.fsync(f.fileno())
            self._seen[key] = encoded
            return True
        finally:
            self.lock_path.rmdir()


class OutcomeTransitionJournal:
    """Research-only state transitions, serialized by an atomic directory lock.

    Fail closed on lock contention; never guess that a stale lock is safe.
    Different correction generations are different evaluation_version_id values.
    """

    TERMINAL = frozenset(("EVALUATED", "MISSING_DATA", "UNKNOWN"))

    def __init__(self, path):
        self.path = Path(path)
        self.lock_path = Path(str(self.path) + ".lock")
        self._states = {}
        self._events = {}
        self._reload()

    def _reload(self):
        self._states = {}
        self._events = {}
        if not self.path.exists():
            return
        with self.path.open("rb") as f:
            for line in f:
                try:
                    row = json.loads(line)
                    event = row["event"]
                    if row["sha256"] != digest(event):
                        raise EvidenceError("transition checksum mismatch")
                    self._apply(event)
                except (ValueError, KeyError, TypeError) as exc:
                    raise EvidenceError("corrupt transition journal") from exc

    def _apply(self, event):
        version = event["evaluation_version_id"]
        state = event["state"]
        if state not in self.TERMINAL | {"PENDING"}:
            raise EvidenceError("invalid transition state")
        sequence = event["sequence"]
        previous = self._states.get(version)
        if sequence != (0 if previous is None else previous["sequence"] + 1):
            raise EvidenceError("transition sequence mismatch")
        if previous is None and state != "PENDING":
            raise EvidenceError("initial transition must be PENDING")
        if previous is not None:
            if previous["state"] != "PENDING" or state == "PENDING":
                raise EvidenceError("illegal transition")
            if event["previous_event_id"] != previous["event_id"]:
                raise EvidenceError("broken transition chain")
        elif event["previous_event_id"] is not None:
            raise EvidenceError("unexpected transition parent")
        if event["event_id"] != digest({k: v for k, v in event.items() if k != "event_id"}):
            raise EvidenceError("transition identity mismatch")
        self._states[version] = {"state": state, "sequence": sequence,
                                 "event_id": event["event_id"]}
        self._events[event["event_id"]] = canonical(event)

    def append(self, evaluation_version_id, state):
        if not evaluation_version_id:
            raise EvidenceError("missing evaluation version")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        try:
            self.lock_path.mkdir()
        except FileExistsError as exc:
            raise EvidenceError("transition journal locked; fail closed") from exc
        try:
            self._reload()  # never trust an in-memory view across processes
            previous = self._states.get(evaluation_version_id)
            if previous is not None and previous["state"] == state:
                return False
            if previous is None and state != "PENDING":
                raise EvidenceError("initial transition must be PENDING")
            if previous is not None and (previous["state"] != "PENDING" or state not in self.TERMINAL):
                raise EvidenceError("illegal transition")
            event = {"evaluation_version_id": evaluation_version_id, "state": state,
                     "sequence": 0 if previous is None else previous["sequence"] + 1,
                     "previous_event_id": None if previous is None else previous["event_id"]}
            event["event_id"] = digest(event)
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("ab") as f:
                f.write((canonical({"event": event, "sha256": digest(event)}) + "\n").encode())
                f.flush()
                os.fsync(f.fileno())
            self._apply(event)
            return True
        finally:
            self.lock_path.rmdir()
