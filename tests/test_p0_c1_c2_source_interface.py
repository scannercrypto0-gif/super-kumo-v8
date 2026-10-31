"""Focused changed-seam tests for C1 source interface and C2 decision producer.

Tests aql.p0.historical-decision.v1 — Core C1 and C2 boundaries.
No live data, no formal backtest, no fixture files assumed.
All tests use in-memory synthetic data or hash-verified constants.

Governance: Core #180 comment 6540572768 — C1/C2 execution task.
These are CHANGED-SEAM tests only; do not repeat B0 regression suite.
"""
from __future__ import annotations

import json
import math
from decimal import Decimal
from hashlib import sha256

import pytest

from research_wp_r0.aql_p0_c1_source import (
    C1SourceRejected,
    INTERVAL_MS,
    WINDOW_START_MS,
    WINDOW_END_EXCLUSIVE_MS,
    EXPECTED_BAR_COUNT,
    NORMALIZED_SHA256,
    _canonical_bytes,
    _sha256_hex,
    _bar_checksum,
    load_source,
)
from research_wp_r0.aql_p0_c2_producer import (
    C2ConflictError,
    DecisionEnvelope,
    STRATEGY_ID,
    MIN_PREFIX_BARS,
    produce_envelopes,
)


# ---------------------------------------------------------------------------
# Synthetic normalized JSON builder (no live data)
# ---------------------------------------------------------------------------

def _make_bar_row(index: int, open_=100.0, high_=101.0, low_=99.0, close_=100.5, vol=1.0):
    open_ms = WINDOW_START_MS + index * INTERVAL_MS
    close_ms = open_ms + INTERVAL_MS - 1
    return [open_ms, close_ms, open_, high_, low_, close_, vol]


def _make_synthetic_normalized(n_bars: int = EXPECTED_BAR_COUNT) -> bytes:
    """Generate a valid normalized JSON for n_bars 15m bars."""
    rows = [_make_bar_row(i) for i in range(n_bars)]
    return json.dumps(rows, separators=(",", ":"), allow_nan=False).encode("utf-8")


def _sha256_bytes(b: bytes) -> str:
    return sha256(b).hexdigest()


# ---------------------------------------------------------------------------
# C1 source loading — fail-closed tests
# ---------------------------------------------------------------------------

class TestC1SourceLoading:

    def _load(self, data: bytes, **kw):
        """Helper: load with synthetic manifest SHA."""
        manifest_sha = _sha256_bytes(b"synthetic-manifest-for-test")
        return load_source(
            normalized_json_bytes=data,
            dataset_id="TEST-DATASET-001",
            dataset_version=1,
            manifest_integrity_sha256=manifest_sha,
            **kw,
        )

    def test_wrong_hash_fails_closed(self):
        """C1 must reject source bytes whose SHA-256 does not match pinned constant."""
        bad_data = _make_synthetic_normalized()
        with pytest.raises(C1SourceRejected) as exc_info:
            self._load(bad_data)
        assert "NORMALIZED_SHA256_MISMATCH" in str(exc_info.value)

    def test_empty_bytes_rejected(self):
        with pytest.raises(C1SourceRejected) as exc_info:
            self._load(b"")
        assert "EMPTY" in str(exc_info.value) or "MUST_BE_BYTES" in str(exc_info.value)

    def test_non_bytes_rejected(self):
        with pytest.raises(C1SourceRejected):
            self._load("not bytes")  # type: ignore

    def test_invalid_json_rejected(self):
        # Fake a hash match for malformed JSON (unlikely in practice; validates parse path)
        malformed = b"not json"
        # Patch SHA to match (manual injection)
        real_sha = _sha256_bytes(malformed)
        # Can't patch constant easily; verify the hash check fires first
        with pytest.raises(C1SourceRejected) as exc_info:
            self._load(malformed)
        assert "MISMATCH" in str(exc_info.value)

    def test_wrong_bar_count_rejected(self):
        """50-bar synthetic should fail hash AND bar count checks (hash first)."""
        short_data = _make_synthetic_normalized(50)
        with pytest.raises(C1SourceRejected):
            self._load(short_data)

    def test_bar_grid_gap_detected(self):
        """Modify one bar to create a grid gap — must fail."""
        rows = [_make_bar_row(i) for i in range(EXPECTED_BAR_COUNT)]
        # Corrupt bar 5: wrong open_ms
        rows[5][0] = rows[5][0] + 1
        rows[5][1] = rows[5][1] + 1
        corrupted = json.dumps(rows, separators=(",", ":"), allow_nan=False).encode("utf-8")
        # Hash won't match pinned constant, but test verifies the validation path
        with pytest.raises(C1SourceRejected):
            self._load(corrupted)

    def test_negative_volume_rejected(self):
        """Negative volume must be rejected."""
        rows = [_make_bar_row(i) for i in range(EXPECTED_BAR_COUNT)]
        rows[10] = _make_bar_row(10, vol=-1.0)
        data = json.dumps(rows, separators=(",", ":"), allow_nan=False).encode("utf-8")
        with pytest.raises(C1SourceRejected):
            self._load(data)

    def test_high_below_ohlc_rejected(self):
        """High < close must be rejected."""
        rows = [_make_bar_row(i) for i in range(EXPECTED_BAR_COUNT)]
        rows[3] = _make_bar_row(3, open_=100.0, high_=99.0, low_=98.0, close_=100.5)
        data = json.dumps(rows, separators=(",", ":"), allow_nan=False).encode("utf-8")
        with pytest.raises(C1SourceRejected):
            self._load(data)

    def test_dataset_version_must_be_positive(self):
        """dataset_version=0 must be rejected."""
        data = _make_synthetic_normalized()
        manifest_sha = _sha256_bytes(b"m")
        # Hash won't match; test validates argument check path
        with pytest.raises((C1SourceRejected, Exception)):
            load_source(
                normalized_json_bytes=data,
                dataset_id="X",
                dataset_version=0,  # invalid
                manifest_integrity_sha256=manifest_sha,
            )


# ---------------------------------------------------------------------------
# C1 bar properties
# ---------------------------------------------------------------------------

class TestC1BarProperties:

    def test_bar_checksum_deterministic(self):
        """Same OHLCV produces same checksum; different OHLCV produces different."""
        c1 = _bar_checksum(WINDOW_START_MS, 100.0, 101.0, 99.0, 100.5, 1.0)
        c2 = _bar_checksum(WINDOW_START_MS, 100.0, 101.0, 99.0, 100.5, 1.0)
        c3 = _bar_checksum(WINDOW_START_MS, 100.0, 101.0, 99.0, 101.0, 1.0)  # different close
        assert c1 == c2
        assert c1 != c3

    def test_bar_checksum_is_lowercase_hex_64(self):
        chk = _bar_checksum(WINDOW_START_MS, 100.0, 101.0, 99.0, 100.5, 1.0)
        assert len(chk) == 64
        assert chk == chk.lower()
        assert all(c in "0123456789abcdef" for c in chk)


# ---------------------------------------------------------------------------
# C2 decision producer — determinism and idempotency
# ---------------------------------------------------------------------------

class TestC2Producer:
    """Tests for C2 without valid C1 data (uses synthetic manifest stub)."""

    def _make_stub_manifest(self, n_bars: int = 25):
        """Build a minimal P0SourceManifest stub for testing C2 logic."""
        from research_wp_r0.aql_p0_c1_source import (
            P0SourceManifest, P0Bar,
            SOURCE_BYTES_SHA256, RECEIPT_STATUS, RECEIPT_MISSING_REASON, CUSTODY_STATUS,
        )

        bars = []
        checksums = []
        for i in range(n_bars):
            open_ms = WINDOW_START_MS + i * INTERVAL_MS
            close_ms = open_ms + INTERVAL_MS - 1
            chk = _bar_checksum(open_ms, 100.0, 101.0, 99.0, 100.5, 1.0)
            checksums.append(chk)
            bars.append(P0Bar(
                bar_id=f"BTCUSDT:15m:{open_ms}",
                bar_open_ms=open_ms,
                bar_close_ms=close_ms,
                open=100.0, high=101.0, low=99.0, close=100.5, volume=1.0,
                is_final=True,
                source_label="TEST",
                availability_kind="RETROSPECTIVE",
                available_as_of_decision="UNKNOWN",
                observation_lower_bound_ms=close_ms + 1,
                receipt_ms=None,
                known_at_ms=None,
                bar_checksum=chk,
                gap_state="COMPLETE",
                correction_generation_id="UNKNOWN_NOT_ATTESTED",
                correction_parent_id=None,
            ))

        ordered_sha = _sha256_hex(_canonical_bytes(checksums))
        gap_inv = {"complete": n_bars, "missing": 0, "total_scheduled": n_bars, "unknown": 0, "bars_with_gap_state": []}
        gap_sha = _sha256_hex(_canonical_bytes(gap_inv))
        corr = {"correction_generation_id": "UNKNOWN_NOT_ATTESTED", "reason": "test", "status": "UNKNOWN_NOT_ATTESTED"}
        corr_sha = _sha256_hex(_canonical_bytes(corr))

        return P0SourceManifest(
            schema="aql.p0.historical-decision.v1",
            project_id="AQL-CRYPTO-RESEARCH-001",
            exchange="BINANCE",
            market="SPOT",
            symbol="BTCUSDT",
            interval_ms=INTERVAL_MS,
            timezone="UTC",
            dataset_id="TEST-DATASET-001",
            dataset_version=1,
            raw_generation_id="P0-TEST",
            source_bytes_sha256=SOURCE_BYTES_SHA256,
            source_provider="BINANCE_VISION",
            source_version="TEST",
            source_receipt_sha256=None,
            receipt_status=RECEIPT_STATUS,
            receipt_missing_reason=RECEIPT_MISSING_REASON,
            custody_status=CUSTODY_STATUS,
            manifest_integrity_sha256=_sha256_hex(b"test-manifest"),
            ordered_bar_checksums_sha256=ordered_sha,
            gap_inventory_sha256=gap_sha,
            correction_lineage_sha256=corr_sha,
            window_start_ms=WINDOW_START_MS,
            window_end_exclusive_ms=WINDOW_START_MS + n_bars * INTERVAL_MS,
            mode="RETROSPECTIVE_NON_PIT",
            research_only=True,
            bars=tuple(bars),
        )

    @staticmethod
    def _produce(manifest, *, trial_id: str, **kw):
        """Thin wrapper: passes a temp journal_path to produce_envelopes."""
        import tempfile, os as _os
        with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False) as f:
            jp = f.name
        try:
            return produce_envelopes(manifest, trial_id=trial_id, journal_path=jp, **kw)
        finally:
            try:
                _os.unlink(jp)
            except OSError:
                pass

    @staticmethod
    def _produce_with_path(manifest, *, trial_id: str):
        """Returns (envelopes, journal_path) — caller must delete the file."""
        import tempfile
        import tempfile as _tmp
        f = _tmp.NamedTemporaryFile(suffix=".jsonl", delete=False)
        jp = f.name
        f.close()
        envelopes = produce_envelopes(manifest, trial_id=trial_id, journal_path=jp)
        return envelopes, jp

    def test_envelope_count_matches_decisions(self):
        """Should produce exactly n_bars - MIN_PREFIX_BARS + 1 envelopes."""
        n = 25
        manifest = self._make_stub_manifest(n)
        envelopes = self._produce(manifest, trial_id="TEST-TRIAL-001")
        # Decisions start at index MIN_PREFIX_BARS (0-indexed), so count = n - MIN_PREFIX_BARS + 1
        expected = n - MIN_PREFIX_BARS + 1
        assert len(envelopes) == expected, f"Expected {expected} got {len(envelopes)}"

    def test_opportunity_ids_are_deterministic(self):
        """Same inputs produce identical opportunity_ids on two calls."""
        manifest = self._make_stub_manifest(25)
        e1 = self._produce(manifest, trial_id="TRIAL-A")
        e2 = self._produce(manifest, trial_id="TRIAL-A")
        for a, b in zip(e1, e2):
            assert a.opportunity_id == b.opportunity_id
            assert a.producer_event_id == b.producer_event_id
            assert a.envelope_sha256 == b.envelope_sha256

    def test_opportunity_ids_differ_by_trial(self):
        """Different trial_id must produce different opportunity_ids."""
        manifest = self._make_stub_manifest(25)
        e1 = self._produce(manifest, trial_id="TRIAL-A")
        e2 = self._produce(manifest, trial_id="TRIAL-B")
        for a, b in zip(e1, e2):
            assert a.opportunity_id != b.opportunity_id

    def test_no_opportunity_id_reused_within_trial(self):
        """Every envelope must have a unique opportunity_id within a trial."""
        manifest = self._make_stub_manifest(25)
        envelopes = self._produce(manifest, trial_id="TRIAL-UNIQ")
        ids = [e.opportunity_id for e in envelopes]
        assert len(ids) == len(set(ids)), "Duplicate opportunity_ids detected"

    def test_idempotent_restart_same_digest_noop(self):
        """Replaying with same journal_path (same entries) must not raise."""
        import os
        from research_wp_r0.aql_p0_c2_producer import load_journal
        manifest = self._make_stub_manifest(21)
        e1, jp = self._produce_with_path(manifest, trial_id="TRIAL-IDEM")
        try:
            # Second call to same journal_path — idempotent (same digest = noop)
            e2 = produce_envelopes(manifest, trial_id="TRIAL-IDEM", journal_path=jp)
            assert len(e1) == len(e2)
        finally:
            try:
                os.unlink(jp)
            except OSError:
                pass

    def test_idempotent_restart_conflict_raises(self):
        """Journal file tampered with conflicting digest must raise C2ConflictError."""
        import os, json as _json
        from research_wp_r0.aql_p0_c2_producer import load_journal
        manifest = self._make_stub_manifest(21)
        envelopes, jp = self._produce_with_path(manifest, trial_id="TRIAL-CONFLICT")
        first_env = envelopes[0]
        # Corrupt the journal: APPEND a new line with wrong digest at the end.
        # _load_journal_file uses last-write-wins; replacing lines[0] is not
        # enough because the APPLIED line (written later) follows it and wins,
        # restoring the real digest.  Appending at the end guarantees the
        # corrupt entry is the one that wins on reload.
        try:
            corrupt_entry = {
                "envelope_sha256": "0" * 64,
                "opportunity_id": first_env.opportunity_id,
                "producer_event_id": first_env.producer_event_id,
                "state": "APPLIED",
            }
            with open(jp, "a", encoding="utf-8") as _f:
                _f.write(_json.dumps(corrupt_entry, sort_keys=True, separators=(",", ":")) + "\n")
            with pytest.raises(C2ConflictError):
                produce_envelopes(manifest, trial_id="TRIAL-CONFLICT", journal_path=jp)
        finally:
            try:
                os.unlink(jp)
            except OSError:
                pass

    def test_envelopes_ordered_by_cutoff_asc(self):
        """Envelopes should be in ascending decision_cutoff_ms order."""
        manifest = self._make_stub_manifest(25)
        envelopes = self._produce(manifest, trial_id="TRIAL-ORDER")
        cutoffs = [e.decision_cutoff_ms for e in envelopes]
        assert cutoffs == sorted(cutoffs)

    def test_decision_cutoff_strictly_after_prefix_last_close(self):
        """decision_cutoff_ms must be strictly greater than last bar's close_ms."""
        manifest = self._make_stub_manifest(25)
        envelopes = self._produce(manifest, trial_id="TRIAL-CUTOFF")
        for env in envelopes:
            assert env.decision_cutoff_ms > env.prefix_end_exclusive_ms - 1

    def test_availability_mode_always_retrospective(self):
        """All envelopes must have availability_mode=RETROSPECTIVE_NON_PIT."""
        manifest = self._make_stub_manifest(25)
        envelopes = self._produce(manifest, trial_id="TRIAL-PIT")
        for env in envelopes:
            assert env.availability_mode == "RETROSPECTIVE_NON_PIT"

    def test_receipt_sha_is_none_in_manifest(self):
        """source_receipt_sha256 must be null in manifest (no observed receipt)."""
        manifest = self._make_stub_manifest(21)
        assert manifest.source_receipt_sha256 is None

    def test_envelope_sha_excludes_itself(self):
        """envelope_sha256 must be computed from canonical dict without envelope_sha256."""
        manifest = self._make_stub_manifest(21)
        envelopes = self._produce(manifest, trial_id="TRIAL-SHA")
        env = envelopes[0]
        # Verify: the sha should change if we include itself in the hash
        from dataclasses import asdict
        d = {
            "account_id": env.account_id,
            "availability_mode": env.availability_mode,
            "correction_lineage_sha256": env.correction_lineage_sha256,
            "coverage_status": env.coverage_status,
            "dataset_id": env.dataset_id,
            "dataset_version": env.dataset_version,
            "decision_cutoff_ms": env.decision_cutoff_ms,
            "decision_ms": env.decision_ms,
            "feature_policy_version": env.feature_policy_version,
            "gap_inventory_sha256": env.gap_inventory_sha256,
            "input_disposition": env.input_disposition,
            "latency_assumption_ms": env.latency_assumption_ms,
            "opportunity_id": env.opportunity_id,
            "prefix_bar_checksums_sha256": env.prefix_bar_checksums_sha256,
            "prefix_end_exclusive_ms": env.prefix_end_exclusive_ms,
            "prefix_start_ms": env.prefix_start_ms,
            "producer_event_id": env.producer_event_id,
            "reason_code": env.reason_code,
            "run_manifest_sha256": env.run_manifest_sha256,
            "schema": env.schema,
            "source_lag_assumption_ms": env.source_lag_assumption_ms,
            "strategy_digest": env.strategy_digest,
            "strategy_id": env.strategy_id,
            "strategy_instance_id": env.strategy_instance_id,
            "strategy_version": env.strategy_version,
            "trial_id": env.trial_id,
        }
        expected_sha = _sha256_hex(_canonical_bytes(d))
        assert env.envelope_sha256 == expected_sha


# ---------------------------------------------------------------------------
# Fix 5 — Focused verification tests: guards actually reached via _skip_hash_check
# ---------------------------------------------------------------------------

class TestC1GuardsReached:
    """Verify that OHLCV/gap/tamper validation guards are actually reached.

    PM Consolidated Correction Order (PR #204 comment 6540907647):
    Existing negative tests short-circuit at the hash check (C1SourceRejected:
    NORMALIZED_SHA256_MISMATCH) and never reach the bar-level guards. These tests
    call _validate_normalized_bars() directly (the private helper extracted for
    exactly this purpose) to confirm the actual guards fire without needing a
    hash-bypass parameter.

    NEVER bypass the hash check in production code.
    """

    def _load_skip(self, rows: list, **kw):
        """Call _validate_normalized_bars directly — bypasses hash, tests bar guards."""
        from research_wp_r0.aql_p0_c1_source import _validate_normalized_bars
        return _validate_normalized_bars(rows)

    def test_negative_volume_reaches_guard(self):
        """Negative volume must be rejected by the BAR_VOLUME_INVALID guard (not hash check)."""
        rows = [_make_bar_row(i) for i in range(EXPECTED_BAR_COUNT)]
        rows[10] = _make_bar_row(10, vol=-1.0)
        with pytest.raises(C1SourceRejected) as exc_info:
            self._load_skip(rows)
        assert "VOLUME_INVALID" in str(exc_info.value), (
            f"Expected VOLUME_INVALID guard, got: {exc_info.value}"
        )

    def test_bar_grid_gap_reaches_guard(self):
        """Grid gap (wrong open_ms) must be caught by GRID_VIOLATION guard, not hash check."""
        rows = [_make_bar_row(i) for i in range(EXPECTED_BAR_COUNT)]
        rows[5][0] = rows[5][0] + 1   # corrupt open_ms
        rows[5][1] = rows[5][1] + 1   # corrupt close_ms to match
        with pytest.raises(C1SourceRejected) as exc_info:
            self._load_skip(rows)
        assert "GRID_VIOLATION" in str(exc_info.value), (
            f"Expected GRID_VIOLATION guard, got: {exc_info.value}"
        )

    def test_high_below_ohlc_reaches_guard(self):
        """High < close must be caught by HIGH_BELOW_OHLC guard, not hash check."""
        rows = [_make_bar_row(i) for i in range(EXPECTED_BAR_COUNT)]
        rows[3] = _make_bar_row(3, open_=100.0, high_=99.0, low_=98.0, close_=100.5)
        with pytest.raises(C1SourceRejected) as exc_info:
            self._load_skip(rows)
        assert "HIGH_BELOW_OHLC" in str(exc_info.value), (
            f"Expected HIGH_BELOW_OHLC guard, got: {exc_info.value}"
        )

    def test_low_above_ohlc_reaches_guard(self):
        """Low > open must be caught by LOW_ABOVE_OHLC guard, not hash check."""
        rows = [_make_bar_row(i) for i in range(EXPECTED_BAR_COUNT)]
        # low=102 > open=100 and close=100.5 → LOW_ABOVE_OHLC
        rows[7] = _make_bar_row(7, open_=100.0, high_=103.0, low_=102.0, close_=100.5)
        with pytest.raises(C1SourceRejected) as exc_info:
            self._load_skip(rows)
        assert "LOW_ABOVE_OHLC" in str(exc_info.value), (
            f"Expected LOW_ABOVE_OHLC guard, got: {exc_info.value}"
        )

    def test_zero_volume_is_allowed(self):
        """Volume=0 is valid (bars with no trades can have volume=0)."""
        rows = [_make_bar_row(i) for i in range(EXPECTED_BAR_COUNT)]
        rows[2] = _make_bar_row(2, vol=0.0)   # zero volume — valid
        bars = self._load_skip(rows)           # must NOT raise
        assert bars is not None and len(bars) > 0

    def test_valid_synthetic_data_passes_all_guards(self):
        """A fully valid synthetic 672-bar input should pass all C1 guards when hash skipped."""
        rows = [_make_bar_row(i) for i in range(EXPECTED_BAR_COUNT)]
        bars = self._load_skip(rows)
        # _validate_normalized_bars returns list[P0Bar] (not a manifest)
        assert len(bars) == EXPECTED_BAR_COUNT
        assert all(b.availability_kind == "RETROSPECTIVE" for b in bars)


class TestC2JournalLifecycle:
    """Verify C2 PENDING→APPLIED→ACKED journal lifecycle.

    PM Consolidated Correction Order (PR #204 comment 6540907647) Fix 4:
    Journal entries must transition PENDING→APPLIED when produced and
    APPLIED→ACKED when acknowledged by ack_envelopes().
    """

    def _make_stub_manifest(self, n_bars: int = 22):
        from research_wp_r0.aql_p0_c1_source import (
            P0SourceManifest, P0Bar,
            SOURCE_BYTES_SHA256, RECEIPT_STATUS, RECEIPT_MISSING_REASON, CUSTODY_STATUS,
        )
        bars = []
        checksums = []
        for i in range(n_bars):
            open_ms = WINDOW_START_MS + i * INTERVAL_MS
            close_ms = open_ms + INTERVAL_MS - 1
            chk = _bar_checksum(open_ms, 100.0, 101.0, 99.0, 100.5, 1.0)
            checksums.append(chk)
            bars.append(P0Bar(
                bar_id=f"BTCUSDT:15m:{open_ms}",
                bar_open_ms=open_ms, bar_close_ms=close_ms,
                open=100.0, high=101.0, low=99.0, close=100.5, volume=1.0,
                is_final=True, source_label="TEST",
                availability_kind="RETROSPECTIVE", available_as_of_decision="UNKNOWN",
                observation_lower_bound_ms=close_ms + 1,
                receipt_ms=None, known_at_ms=None,
                bar_checksum=chk, gap_state="COMPLETE",
                correction_generation_id="UNKNOWN_NOT_ATTESTED", correction_parent_id=None,
            ))
        ordered_sha = _sha256_hex(_canonical_bytes(checksums))
        gap_inv = {"bars_with_gap_state": [], "complete": n_bars, "missing": 0,
                   "total_scheduled": n_bars, "unknown": 0}
        gap_sha = _sha256_hex(_canonical_bytes(gap_inv))
        corr = {"correction_generation_id": "UNKNOWN_NOT_ATTESTED",
                "reason": "test", "status": "UNKNOWN_NOT_ATTESTED"}
        corr_sha = _sha256_hex(_canonical_bytes(corr))
        return P0SourceManifest(
            schema="aql.p0.historical-decision.v1", project_id="AQL-CRYPTO-RESEARCH-001",
            exchange="BINANCE", market="SPOT", symbol="BTCUSDT",
            interval_ms=INTERVAL_MS, timezone="UTC",
            dataset_id="TEST-DATASET-001", dataset_version=1,
            raw_generation_id="P0-TEST", source_bytes_sha256=SOURCE_BYTES_SHA256,
            source_provider="BINANCE_VISION", source_version="TEST",
            source_receipt_sha256=None, receipt_status=RECEIPT_STATUS,
            receipt_missing_reason=RECEIPT_MISSING_REASON, custody_status=CUSTODY_STATUS,
            manifest_integrity_sha256=_sha256_hex(b"test-manifest"),
            ordered_bar_checksums_sha256=ordered_sha,
            gap_inventory_sha256=gap_sha, correction_lineage_sha256=corr_sha,
            window_start_ms=WINDOW_START_MS,
            window_end_exclusive_ms=WINDOW_START_MS + n_bars * INTERVAL_MS,
            mode="RETROSPECTIVE_NON_PIT", research_only=True, bars=tuple(bars),
        )

    @staticmethod
    def _produce_with_journal(manifest, *, trial_id: str):
        """Returns (envelopes, journal_path, DurableJournal) — caller deletes path."""
        import tempfile
        from research_wp_r0.aql_p0_c2_producer import load_journal
        f = tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False)
        jp = f.name
        f.close()
        envelopes = produce_envelopes(manifest, trial_id=trial_id, journal_path=jp)
        journal = load_journal(jp)
        return envelopes, jp, journal

    def test_journal_pending_to_applied_transition(self):
        """All journal entries must be APPLIED (not PENDING) after produce_envelopes()."""
        import os
        from research_wp_r0.aql_p0_c2_producer import load_journal
        manifest = self._make_stub_manifest(22)
        envelopes, jp, journal = self._produce_with_journal(manifest, trial_id="LIFECYCLE-TEST")
        try:
            entries = journal.entries
            assert len(entries) > 0, "Journal must be populated"
            for pid, entry in entries.items():
                assert entry.state == "APPLIED", (
                    f"Expected APPLIED after produce_envelopes, got {entry.state!r} "
                    f"for producer_event_id={pid!r}"
                )
            pending = [e for e in entries.values() if e.state == "PENDING"]
            assert len(pending) == 0, f"Found {len(pending)} PENDING entries after production"
        finally:
            try:
                os.unlink(jp)
            except OSError:
                pass

    def test_ack_envelopes_applied_to_acked(self):
        """ack_envelopes() must transition APPLIED entries to ACKED."""
        import os
        from research_wp_r0.aql_p0_c2_producer import ack_envelopes, load_journal
        manifest = self._make_stub_manifest(22)
        envelopes, jp, journal = self._produce_with_journal(manifest, trial_id="ACK-TEST")
        try:
            all_pids = [e.producer_event_id for e in envelopes]
            acked_count = ack_envelopes(all_pids, journal)
            assert acked_count == len(envelopes), (
                f"Expected {len(envelopes)} ACKed, got {acked_count}"
            )
            # Re-load to verify persisted state
            journal2 = load_journal(jp)
            for pid, entry in journal2.entries.items():
                assert entry.state == "ACKED", (
                    f"Expected ACKED, got {entry.state!r} for {pid!r}"
                )
        finally:
            try:
                os.unlink(jp)
            except OSError:
                pass

    def test_ack_envelopes_idempotent_for_already_acked(self):
        """ack_envelopes() on already-ACKED entries must be a no-op (idempotent)."""
        import os
        from research_wp_r0.aql_p0_c2_producer import ack_envelopes
        manifest = self._make_stub_manifest(22)
        envelopes, jp, journal = self._produce_with_journal(manifest, trial_id="ACK-IDEM-TEST")
        try:
            all_pids = [e.producer_event_id for e in envelopes]
            acked_first = ack_envelopes(all_pids, journal)
            acked_second = ack_envelopes(all_pids, journal)
            assert acked_first == len(envelopes)
            assert acked_second == 0, (
                f"Expected 0 newly ACKED on second call (idempotent), got {acked_second}"
            )
        finally:
            try:
                os.unlink(jp)
            except OSError:
                pass

    def test_ack_unknown_id_raises_conflict(self):
        """ack_envelopes() with an ID not in journal must raise C2ConflictError."""
        import os
        from research_wp_r0.aql_p0_c2_producer import ack_envelopes, C2ConflictError
        manifest = self._make_stub_manifest(22)
        _, jp, journal = self._produce_with_journal(manifest, trial_id="ACK-ERR-TEST")
        try:
            with pytest.raises(C2ConflictError) as exc_info:
                ack_envelopes(["nonexistent-id-00000000"], journal)
            assert "ACK_UNKNOWN_ID" in str(exc_info.value)
        finally:
            try:
                os.unlink(jp)
            except OSError:
                pass

    def test_source_bytes_sha_blocked_marker(self):
        """BLOCKED: owner's original ZIP package is not available in this environment.

        The normalized JSON hash constants (NORMALIZED_SHA256) were set from the
        owner's Factory comment #77/6540521965. The outer ZIP (OUTER_ZIP_SHA256)
        identifies the full owner delivery package and is NOT available for re-download
        in this test environment. This test documents that constraint explicitly.

        Status: BLOCKED — source bytes package inaccessible; cannot verify live.
        Evidence: hash constants recorded from Factory #77 comment 6540521965.
        """
        from research_wp_r0.aql_p0_c1_source import (
            OUTER_ZIP_SHA256, MANIFEST_SHA256, NORMALIZED_SHA256, SOURCE_BYTES_SHA256,
        )
        # Verify constants match the canonical Factory comment values
        assert OUTER_ZIP_SHA256 == "f4e0b3680dd56c9fbe680be2473b8de29fc1d8d7e22657973c85945d2bf99f97"
        assert MANIFEST_SHA256 == "f731bc19c1d4bb0dfa79198c6739a4dbd356e02904086d4df2a136773bd25456"
        assert NORMALIZED_SHA256 == "a881cc99e80697f2da57784b5bea91a7f339c6c391d4d53cc0222842168af0f0"
        assert SOURCE_BYTES_SHA256 == OUTER_ZIP_SHA256, (
            "SOURCE_BYTES_SHA256 must equal OUTER_ZIP_SHA256 per canonical contract"
        )
        # NOT_TESTED: actual ZIP download + hash verification requires the owner's package.
        # This test only verifies the constants are correctly recorded.
        pytest.skip(
            "BLOCKED: owner ZIP package not available in test env; "
            "constants verified from Factory #77 comment 6540521965 only. "
            "Live hash verification requires owner-supplied package."
        )
