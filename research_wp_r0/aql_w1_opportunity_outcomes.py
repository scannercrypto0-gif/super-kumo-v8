"""W1 research-only opportunity outcomes. No paper/order/position imports.

Retrospective market excursions are NOT fills, PIT observations, or realized PnL.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
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
    def snapshot_id(self):
        return digest({"schema": 1, **asdict(self)})


def reconcile(envelopes, selections):
    """Exact 1:1 immutable source join; no outcome-based eligibility inference."""
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
        for field in ("signal_state", "reason_code", "decision_cutoff_ms"):
            if e.get(field) != s.get(field):
                raise EvidenceError("conflicting source " + field)
        result.append(RetrospectiveSnapshot(
            trial_id=e["trial_id"], manifest_sha256=e["run_manifest_sha256"],
            opportunity_id=e["opportunity_id"], producer_event_id=e["producer_event_id"],
            envelope_sha256=e["envelope_sha256"], decision_cutoff_ms=e["decision_cutoff_ms"],
            decision_ms=e["decision_ms"], signal_state=e["signal_state"],
            reason_code=e.get("reason_code"), direction=s.get("direction"),
            eligibility=s.get("eligibility", "NOT_ESTABLISHED"),
            eligibility_evidence=s.get("eligibility_evidence"),
            context_digest=s["context_digest"],
        ))
    if len(seen) != len(by_id):
        raise EvidenceError("orphan selection")
    return tuple(result)


def market_outcome(snapshot, horizon_ms, bars, *, source_version, source_end_exclusive_ms,
                   archive_finalized=True, policy_version="W1-MARKET-v1"):
    """bars are OHLC dicts with open_ms/open/high/low/close and finalized flag.

    OPEN(t) is a non-executable retrospective reference; the modeled decision
    may occur later. All H/15m finalized bars are required, no partial MFE.
    """
    if horizon_ms not in HORIZONS:
        raise EvidenceError("unsupported horizon")
    t = snapshot.decision_cutoff_ms
    due = t + horizon_ms
    key = {"snapshot_id": snapshot.snapshot_id, "horizon_ms": horizon_ms,
           "source_version": source_version, "policy_version": policy_version}
    result = {"outcome_id": digest(key), **key, "due_at_ms": due,
              "reference_kind": "OPEN_AT_CUTOFF_NON_EXECUTABLE",
              "execution_status": "NOT_OBSERVED", "order_resolution": "UNKNOWN",
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
    result.update(status="EVALUATED", reason=None, mfe=favorable, mae=adverse,
                  order_resolution="NOT_APPLICABLE", bar_count=len(ordered),
                  reference_price=base)
    return result


class AppendOnlyOutcomeJournal:
    """fsync + deterministic idempotent replay. No position side effects."""

    def __init__(self, path):
        self.path = Path(path)
        self._seen = {}
        if self.path.exists():
            with self.path.open("rb") as f:
                for line in f:
                    try:
                        record = json.loads(line)
                        payload = record["payload"]
                        if record["sha256"] != digest(payload):
                            raise EvidenceError("journal checksum mismatch")
                        self._accept(payload)
                    except (ValueError, KeyError, TypeError) as exc:
                        raise EvidenceError("corrupt journal; fail closed") from exc

    def _accept(self, payload):
        key = payload["outcome_id"]
        encoded = canonical(payload)
        if key in self._seen and self._seen[key] != encoded:
            raise EvidenceError("conflicting outcome generation")
        old = key in self._seen
        self._seen[key] = encoded
        return not old

    def append(self, payload):
        key = payload["outcome_id"]
        encoded = canonical(payload)
        if key in self._seen:
            if self._seen[key] != encoded:
                raise EvidenceError("conflicting outcome generation")
            return False
        record = (canonical({"payload": payload, "sha256": digest(payload)}) + "\n").encode()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("ab") as f:
            f.write(record)
            f.flush()
            os.fsync(f.fileno())
        self._seen[key] = encoded
        return True
