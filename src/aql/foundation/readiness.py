"""Versioned per-decision feature admission over existing G1 journal/store.

This checks availability, not indicator formulas. Existing versioned indicator
libraries remain the computation owners. No provisional fallback is implicit.
"""
from dataclasses import dataclass
import json
import sqlite3
from pathlib import Path
from ..models.bar import MarketBar
from ..g1_integrity import content, fingerprint, receipt, require_eligible_db


def _read(journal, store, symbol, interval, first, last):
    from ..delivery.authority import deny_legacy
    from ..delivery.store_binding import deny_store_legacy
    # Existing public get_range APIs return bounds, not bar records. This
    # adapter uses read-only connections and respects existing writer guards.
    result = []
    for obj, table, guard in ((journal, "journal_entries", deny_legacy),
                              (store, "market_bars", deny_store_legacy)):
        conn = sqlite3.connect(Path(obj.db_path).resolve().as_uri() + "?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
        try:
            conn.execute("BEGIN")
            guard(conn)
            rows = conn.execute(f"SELECT * FROM {table} WHERE symbol=? AND interval=? "
                                "AND bar_open>=? AND bar_open<=? ORDER BY bar_open LIMIT 10001",
                                (symbol, interval, first, last)).fetchall()
            if len(rows) > 10000:
                raise ValueError("Source window exceeds bound")
            bars, receipts = {}, {}
            for row in rows:
                payload = json.loads(row["payload_json"]) if table == "journal_entries" else dict(row)
                if table == "market_bars":
                    payload.pop("id")
                    if payload["is_final"] not in (0, 1):
                        raise ValueError("Invalid final flag")
                    payload["is_final"] = bool(payload["is_final"])
                b = MarketBar.from_dict(payload)
                require_eligible_db(conn, b.stable_key())
                if row["checksum"] != b.compute_checksum():
                    raise ValueError("Source checksum mismatch")
                bars[b.bar_open] = b
                if table == "journal_entries":
                    r = receipt(conn, "BAR", b.stable_key())
                    if r.get("content_digest") != fingerprint(content(b)):
                        raise ValueError("Commit receipt missing or mismatched")
                    marker = conn.execute("SELECT version FROM g1_record_contracts WHERE stable_key=?",
                                          (b.stable_key(),)).fetchone()
                    if marker is None or marker[0] != 1:
                        raise ValueError("Unverified record contract")
                    receipts[b.bar_open] = r
            result.append((bars, receipts))
        finally:
            conn.close()
    return result


@dataclass(frozen=True)
class FeatureRequirement:
    feature_id: str
    version: str
    warmup: int

    def __post_init__(self):
        if not self.feature_id or not self.version or type(self.warmup) is not int or not 1 <= self.warmup <= 10000:
            raise ValueError("Invalid feature requirement")


def assess(journal, store, *, symbol, interval, opens, requirements,
           available_versions, decision_ms, clock_verified, interval_ms=60000):
    """Read a bounded, explicitly requested contiguous window; never write ACKs.

    available_versions identifies the caller's frozen computation catalog.
    READY means source availability for those versions, not a computed result
    or independently authenticated clock. Trust in clock proof stays upstream.
    """
    if type(decision_ms) is not int or decision_ms < 0:
        raise ValueError("Invalid decision time")
    if type(interval_ms) is not int or interval_ms <= 0:
        raise ValueError("Invalid interval")
    opens, requirements = tuple(opens), tuple(requirements)
    if (not opens or len(opens) > 10000 or len(requirements) > 128
            or any(type(t) is not int or t < 0 or t % interval_ms for t in opens)
            or any(b - a != interval_ms for a, b in zip(opens, opens[1:]))):
        raise ValueError("Invalid bounded source window")
    if len({r.feature_id for r in requirements}) != len(requirements) or not requirements:
        raise ValueError("Invalid decision requirements")
    reasons = []
    if clock_verified is not True:
        reasons.append("CLOCK_UNVERIFIED")
    # Bounded read snapshots, followed by current quarantine checks. This is
    # availability evidence, not a transaction spanning a later consumer use.
    try:
        (committed, receipts), (bars, _) = _read(journal, store, symbol, interval, opens[0], opens[-1])
    except (ValueError, RuntimeError, sqlite3.Error):
        committed, receipts, bars = {}, {}, {}
        reasons.append("SOURCE_UNVERIFIED_OR_CONFLICT")
    source = []
    for opened in opens:
        b = bars.get(opened)
        if b is None:
            reasons.append("MISSING_BAR")
            continue
        try:
            journal.require_eligible(b.stable_key())
            store.require_eligible(b.stable_key())
            commit = receipts.get(opened, {})
            persisted = committed.get(opened)
            if persisted is None or persisted.compute_checksum() != b.compute_checksum():
                reasons.append("JOURNAL_STORE_MISMATCH")
            if persisted is not None and (type(persisted.ingested_at) is not int
                                         or persisted.ingested_at > decision_ms):
                reasons.append("FUTURE_OR_INVALID_BAR")
            if (commit.get("status") != "SQLITE_COMMIT_RETURN_OBSERVED"
                    or commit.get("commit_return_observed_at_ms", decision_ms + 1) > decision_ms):
                reasons.append("COMMIT_NOT_AVAILABLE_ASOF")
        except (ValueError, RuntimeError):
            reasons.append("SOURCE_UNVERIFIED_OR_CONFLICT")
        if b.is_final is not True:
            reasons.append("PROVISIONAL_BAR")
        if (b.bar_close != opened + interval_ms - 1 or b.bar_close >= decision_ms
                or type(b.ingested_at) is not int or b.ingested_at > decision_ms):
            reasons.append("FUTURE_OR_INVALID_BAR")
        if b.checksum != b.compute_checksum():
            reasons.append("CHECKSUM_MISMATCH")
        source.append(b.compute_checksum())
    features = []
    for r in requirements:
        why = list(reasons)
        if available_versions.get(r.feature_id) != r.version:
            why.append("VERSION_UNAVAILABLE")
        if len(opens) < r.warmup:
            why.append("WARMUP_INCOMPLETE")
        features.append(dict(feature_id=r.feature_id, version=r.version,
                             ready=not why, reasons=sorted(set(why))))
    return dict(schema="aql.g1.readiness.v1", decision_ms=decision_ms,
                symbol=symbol, interval=interval, source_checksums=source,
                ready=all(f["ready"] for f in features), features=features)
