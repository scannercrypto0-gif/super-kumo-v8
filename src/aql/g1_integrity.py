"""Core-local additive receipts/quarantine. No MarketBar/Factory schema changes.

SQLite FULL commit-return observation is software evidence, NOT a physical
fsync completion measurement, independent custody, or power-loss guarantee.
"""
from __future__ import annotations

import hashlib
import json
import math
import time


class CommitEvidenceError(RuntimeError):
    """Data may be committed, but a new completion receipt was not established."""


class ContentConflictError(ValueError):
    def __init__(self, evidence):
        self.evidence = json.loads(canonical(evidence))
        self.stable_key = evidence["stable_key"]
        super().__init__(f"Quarantined conflicting content: {self.stable_key}")


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def fingerprint(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def content(bar):
    """Version1 candle facts. Transport/receipt/state are separate provenance.

    Same WS/REST candle facts are an identical retry; original provenance is
    never overwritten. Legacy MarketBar.compute_checksum remains unchanged.
    """
    prices = {}
    for name in ("open", "high", "low", "close", "volume"):
        value = float(getattr(bar, name))
        if not math.isfinite(value):
            raise ValueError("Nonfinite candle content")
        prices[name] = 0.0 if value == 0 else value
    return dict(version=1, symbol=bar.symbol, interval=bar.interval,
                bar_open=bar.bar_open, bar_close=bar.bar_close,
                is_final=bool(bar.is_final), **prices)


def init_integrity(conn):
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS g1_record_contracts (
      stable_key TEXT PRIMARY KEY, version INTEGER NOT NULL CHECK(version=1));
    CREATE TABLE IF NOT EXISTS g1_commit_receipts (
      kind TEXT NOT NULL, identity TEXT NOT NULL, version INTEGER NOT NULL,
      content_digest TEXT NOT NULL, commit_return_observed_at_ms INTEGER NOT NULL,
      PRIMARY KEY(kind, identity));
    CREATE TABLE IF NOT EXISTS g1_integrity_events (
      event_id TEXT PRIMARY KEY, stable_key TEXT NOT NULL,
      symbol TEXT NOT NULL, interval TEXT NOT NULL, evidence_json TEXT NOT NULL);
    CREATE INDEX IF NOT EXISTS g1_integrity_scope ON g1_integrity_events(symbol,interval,stable_key);
    CREATE TRIGGER IF NOT EXISTS g1_integrity_no_update BEFORE UPDATE ON g1_integrity_events
      BEGIN SELECT RAISE(ABORT,'append-only integrity evidence'); END;
    CREATE TRIGGER IF NOT EXISTS g1_integrity_no_delete BEFORE DELETE ON g1_integrity_events
      BEGIN SELECT RAISE(ABORT,'append-only integrity evidence'); END;
    CREATE TRIGGER IF NOT EXISTS g1_receipt_no_update BEFORE UPDATE ON g1_commit_receipts
      BEGIN SELECT RAISE(ABORT,'immutable commit receipt'); END;
    CREATE TRIGGER IF NOT EXISTS g1_receipt_no_delete BEFORE DELETE ON g1_commit_receipts
      BEGIN SELECT RAISE(ABORT,'immutable commit receipt'); END;
    CREATE TRIGGER IF NOT EXISTS g1_contract_no_update BEFORE UPDATE ON g1_record_contracts
      BEGIN SELECT RAISE(ABORT,'immutable record contract'); END;
    CREATE TRIGGER IF NOT EXISTS g1_contract_no_delete BEFORE DELETE ON g1_record_contracts
      BEGIN SELECT RAISE(ABORT,'immutable record contract'); END;
    """)


def post_commit_receipt(conn, kind, identity, content_digest, not_before_ms):
    """Call ONLY after the target transaction COMMIT has returned successfully.

    Separate receipt transaction: a crash/failure between transactions means
    data without a receipt, never inferred post-success timestamp evidence.
    """
    observed = int(time.time() * 1000)
    if observed < not_before_ms:
        raise CommitEvidenceError("Clock moved backwards; completion time unverified")
    try:
        conn.execute("BEGIN IMMEDIATE")
        conn.execute("INSERT OR IGNORE INTO g1_commit_receipts VALUES (?,?,1,?,?)",
                     (kind, identity, content_digest, observed))
        conn.execute("COMMIT")
    except Exception as exc:
        if conn.in_transaction:
            conn.execute("ROLLBACK")
        raise CommitEvidenceError("Target may be committed; completion receipt unavailable") from exc


def receipt(conn, kind, identity):
    row = conn.execute("SELECT version,content_digest,commit_return_observed_at_ms "
                       "FROM g1_commit_receipts WHERE kind=? AND identity=?", (kind, identity)).fetchone()
    if row is None:
        return {"version": 0, "status": "LEGACY_OR_UNCONFIRMED", "commit_return_observed_at_ms": None}
    if row[0] != 1:
        raise CommitEvidenceError("Unsupported receipt version; no completion proof")
    return dict(version=row[0], status="SQLITE_COMMIT_RETURN_OBSERVED", content_digest=row[1],
                commit_return_observed_at_ms=row[2], physical_fsync_or_powerloss_verified=False)


def require_eligible_db(conn, key):
    # Legacy archive readers can open an original database without migration.
    if not conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='g1_integrity_events'").fetchone():
        return
    row = conn.execute("SELECT evidence_json FROM g1_integrity_events WHERE stable_key=? LIMIT 1", (key,)).fetchone()
    if row:
        raise ContentConflictError(json.loads(row[0]))


def record_event(conn, original, incoming, *, kind="DUPLICATE_CONFLICT", reason="identity-content mismatch"):
    if original.stable_key() != incoming.stable_key():
        raise ValueError("Evidence identities differ")
    core = dict(version=1, kind=kind, stable_key=original.stable_key(),
                original_content=content(original), incoming_content=content(incoming),
                incoming_source=incoming.source, incoming_receipt_ms=incoming.ingested_at,
                reason=reason)
    event_id = fingerprint(core)
    evidence = dict(core, event_id=event_id, detected_at_ms=int(time.time()*1000),
                    original_record=original.to_dict(), incoming_record=incoming.to_dict(),
                    decision_eligible=False, resolution="PENDING_OWNER_REVIEW")
    conn.execute("INSERT OR IGNORE INTO g1_integrity_events VALUES (?,?,?,?,?)",
                 (event_id, original.stable_key(), original.symbol, original.interval, canonical(evidence)))
    stored = conn.execute("SELECT evidence_json FROM g1_integrity_events WHERE event_id=?", (event_id,)).fetchone()
    from .delivery.authority import conflict_in_transaction
    conflict_in_transaction(conn, original.stable_key())
    return json.loads(stored[0])


class IntegrityAccess:
    """Core DB mixin; original facts persist, quarantine never auto-clears."""
    def require_eligible(self, key):
        conn = self._connect()
        try:
            require_eligible_db(conn, key)
        finally:
            conn.close()

    def quarantined_keys(self, symbol=None, interval=None):
        conn = self._connect()
        try:
            query, args = "SELECT DISTINCT stable_key FROM g1_integrity_events WHERE 1=1", []
            if symbol is not None:
                query += " AND symbol=?"; args.append(symbol)
            if interval is not None:
                query += " AND interval=?"; args.append(interval)
            return {r[0] for r in conn.execute(query, args)}
        finally:
            conn.close()

    def conflict_evidence(self, key):
        conn = self._connect()
        try:
            records = []
            for row in conn.execute("SELECT event_id,evidence_json FROM g1_integrity_events WHERE stable_key=? ORDER BY rowid", (key,)):
                value = json.loads(row[1])
                proof = receipt(conn,"AUDIT",row[0])
                if proof["version"] and proof["content_digest"] != fingerprint(value):
                    raise ValueError("Audit receipt/content mismatch")
                value["audit_availability_receipt"] = proof
                records.append(value)
            return records
        finally:
            conn.close()

    def quarantine(self, error):
        from .models.bar import MarketBar
        data = error.evidence
        original = MarketBar.from_dict(data["original_record"])
        incoming = MarketBar.from_dict(data["incoming_record"])
        return self._record_integrity_event(original,incoming,reason=data["reason"])

    def record_correction(self, original, corrected, *, reason):
        """Append a NEW audit proposal, not replacement or automatic resolution.

        A new receipt and post-audit-commit availability observation are retained;
        no past decision changes and no decision eligibility granted.
        """
        if (not reason or corrected.ingested_at <= original.ingested_at
                or corrected.ingested_at > int(time.time()*1000)):
            raise ValueError("Correction requires a reason and new arrival provenance")
        return self._record_integrity_event(original,corrected,kind="CORRECTION_PROPOSAL",reason=reason)

    def _record_integrity_event(self, original, incoming, **kwargs):
        from .delivery.authority import prepare_candidate
        prepare_candidate(self,incoming,force=True)
        conn = self._connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            local = self._original_bar(conn,original.stable_key())
            if kwargs.get("kind") == "CORRECTION_PROPOSAL":
                if local is None or local.to_dict() != original.to_dict():
                    raise ValueError("Correction must reference the actual retained original")
            elif local is not None:
                # Cross-store divergence: retain the alternative facts, never
                # label the remote copy as this DB's authoritative original.
                if content(local) == content(incoming):
                    incoming = original
                original = local
            evidence = record_event(conn,original,incoming,**kwargs)
            conn.execute("COMMIT")
            post_commit_receipt(conn,"AUDIT",evidence["event_id"],fingerprint(evidence),evidence["detected_at_ms"])
            return evidence["event_id"]
        except Exception:
            if conn.in_transaction: conn.execute("ROLLBACK")
            raise
        finally:
            conn.close()


def propagate_conflict(error, *targets):
    """Mirror quarantine only; never turn propagation failure into an ACK."""
    failures = []
    for target in targets:
        try:
            target.quarantine(error)
        except Exception as exc:
            failures.append(exc)
    if failures:
        raise CommitEvidenceError("Conflict propagation incomplete; no ACK permitted") from failures[0]
