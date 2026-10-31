"""Adversarial tests for C1/C2/F3/F4 blockers.

These tests are DESIGNED to:
  - FAIL on the baseline (fe40f4a) where each blocker exists
  - PASS after the fixes applied in this PR

Evidence class: SYNTHETIC_ONLY
(real outer ZIP bytes not available in Claude runner environment — C1 real admission = BLOCKED_REAL_SOURCE)
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Path setup
# ---------------------------------------------------------------------------
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from research_wp_r0.aql_p0_c1_source import (
    C1SourceRejected,
    P0Bar,
    P0SourceManifest,
    _sha256_hex,
    _canonical_bytes,
    _validate_normalized_bars,
    admit_source,
    load_source,
    OUTER_ZIP_SHA256,
    MANIFEST_SHA256,
    NORMALIZED_SHA256,
    WINDOW_START_MS,
    EXPECTED_BAR_COUNT,
    INTERVAL_MS as BAR_DURATION_MS,
)
from research_wp_r0.aql_p0_c2_producer import (
    DurableJournal,
    C2ConflictError,
    load_journal,
    produce_envelopes,
    ack_envelopes,
)
from research_wp_r0.aql_p0_f1f2_opportunities import (
    Opportunity,
    SignalState,
)
from research_wp_r0.aql_p0_f3_fill_model import (
    model_fills,
    FillResult,
    INITIAL_CASH,
    POSITION_SIZE_BTC,
)
from research_wp_r0.aql_p0_f4_ledger import (
    LedgerConflictError,
    LedgerReceiptCorrupted,
    LedgerReportCorrupted,
    FinancialReceipt,
    build_ledger,
    persist_report,
    load_report,
    persist_receipts,
    load_receipts,
    reconcile_receipts,
)


# ===========================================================================
# C1 ADVERSARIAL TESTS
# ===========================================================================

class TestC1AdmitSourceBlocker:
    """C1: admit_source() must reject missing or mismatched bytes."""

    def test_admit_source_none_outer_zip_raises(self):
        """FAIL on baseline: _skip_hash_check existed; fix: admit_source raises BLOCKED_REAL_SOURCE."""
        fake_normalized = b'{"bars": []}'
        with pytest.raises(C1SourceRejected, match="BLOCKED_REAL_SOURCE"):
            admit_source(
                outer_zip_bytes=None,
                manifest_bytes=b"{}",
                normalized_bytes=fake_normalized,
            )

    def test_admit_source_none_manifest_raises(self):
        """FAIL on baseline: no separate manifest check; fix: raises BLOCKED_REAL_SOURCE."""
        with pytest.raises(C1SourceRejected, match="BLOCKED_REAL_SOURCE"):
            admit_source(
                outer_zip_bytes=b"fake_outer",
                manifest_bytes=None,
                normalized_bytes=b"{}",
            )

    def test_admit_source_wrong_outer_hash(self):
        """Tampered outer ZIP bytes → OUTER_ZIP_SHA256_MISMATCH."""
        tampered = b"tampered_outer_zip_bytes"
        with pytest.raises(C1SourceRejected, match="OUTER_ZIP_SHA256_MISMATCH"):
            admit_source(
                outer_zip_bytes=tampered,
                manifest_bytes=b"{}",
                normalized_bytes=b"{}",
            )

    def test_admit_source_wrong_manifest_hash(self):
        """OUTER check fires before MANIFEST check — order is enforced.

        EVIDENCE_CLASS: SYNTHETIC_ONLY
        NOTE: The MANIFEST_SHA256_MISMATCH path (outer passes, manifest fails) is
        BLOCKED in a synthetic environment because we cannot produce outer_zip_bytes
        whose SHA256 equals OUTER_ZIP_SHA256 without the real source file.
        What we CAN verify is that admit_source() checks OUTER first, so tampered
        outer bytes always produce OUTER_ZIP_SHA256_MISMATCH before reaching the
        manifest check. The manifest-gate itself is separately unit-tested via
        _validate_normalized_bars() which is reachable without the outer ZIP.
        """
        with pytest.raises(C1SourceRejected) as exc_info:
            admit_source(
                outer_zip_bytes=b"wrong_outer",
                manifest_bytes=b"wrong_manifest",
                normalized_bytes=b"{}",
            )
        # OUTER check fires first → OUTER_ZIP_SHA256_MISMATCH (not MANIFEST)
        assert "OUTER_ZIP_SHA256_MISMATCH" in str(exc_info.value)

    def test_load_source_no_skip_hash_check_param(self):
        """FAIL on baseline: _skip_hash_check and normalized_json_bytes were public params.
        Fix: new signature only accepts 'admitted: AdmittedSource'; all old kwargs are
        rejected with TypeError — bypassing the admission gate is structurally impossible.

        Note: match parameter omitted intentionally — after the signature change the error
        mentions 'normalized_json_bytes' as the first unknown kwarg, not '_skip_hash_check'.
        The critical property is that ANY old-style call raises TypeError.
        """
        with pytest.raises(TypeError):
            load_source(
                normalized_json_bytes=b"{}",       # type: ignore[call-arg]
                dataset_id="TEST",
                manifest_integrity_sha256="abc",   # type: ignore[call-arg]
                _skip_hash_check=True,             # type: ignore[call-arg]
            )

    def test_validate_normalized_bars_directly(self):
        """_validate_normalized_bars() can be called directly for bar-level tests
        without having real source bytes.
        This tests the EXTRACTED helper is accessible.
        """
        # Empty list → should raise C1SourceRejected (not enough bars)
        with pytest.raises(C1SourceRejected):
            _validate_normalized_bars([])

    def test_validate_normalized_bars_wrong_count(self):
        """Wrong bar count → C1SourceRejected."""
        # Construct one valid bar dict
        bar_open = WINDOW_START_MS
        bar = {
            "bar_open_ms": bar_open,
            "bar_close_ms": bar_open + BAR_DURATION_MS - 1,
            "open": 42000.0,
            "high": 43000.0,
            "low": 41000.0,
            "close": 42500.0,
            "volume": 1.5,
            "receipt_ms": None,
            "known_at_ms": None,
            "availability_kind": "RETROSPECTIVE",
            "observation_lower_bound_ms": bar_open + BAR_DURATION_MS,
        }
        with pytest.raises(C1SourceRejected):
            _validate_normalized_bars([bar])  # 1 bar, need EXPECTED_BAR_COUNT


# ===========================================================================
# C2 ADVERSARIAL TESTS
# ===========================================================================

class TestC2DurableJournal:
    """C2: DurableJournal must survive crash + restart with no double-effect."""

    def _make_manifest(self, tmp_path: Path) -> "P0SourceManifest":
        """Build a minimal manifest with enough bars for testing."""
        bars = []
        for i in range(EXPECTED_BAR_COUNT):
            open_ms = WINDOW_START_MS + i * BAR_DURATION_MS
            bars.append(P0Bar(
                bar_id=f"BAR-{i:04d}",
                bar_open_ms=open_ms,
                bar_close_ms=open_ms + BAR_DURATION_MS - 1,
                open=42000.0 + i * 10,
                high=43000.0 + i * 10,
                low=41000.0 + i * 10,
                close=42500.0 + i * 10,
                volume=1.5,
                is_final=True,
                source_label="SYNTHETIC",
                availability_kind="RETROSPECTIVE",
                available_as_of_decision=None,
                observation_lower_bound_ms=open_ms + BAR_DURATION_MS,
                receipt_ms=None,
                known_at_ms=None,
                bar_checksum=_sha256_hex(str(i).encode()),
                gap_state="NO_GAP",
                correction_generation_id="UNKNOWN_NOT_ATTESTED",
                correction_parent_id=None,
            ))
        return P0SourceManifest(
            dataset_id="TEST",
            dataset_version=1,
            raw_generation_id="P0-DEV-2024-01-01-TO-2024-01-08",
            correction_generation_id="UNKNOWN_NOT_ATTESTED",
            manifest_integrity_sha256=_sha256_hex(b"synthetic"),
            bars=bars,
        )

    def test_duplicate_same_id_same_digest_is_noop(self, tmp_path):
        """C2: same id+digest → idempotent NO-OP on second write_pending call."""
        journal_path = tmp_path / "journal.jsonl"
        j = DurableJournal(journal_path)
        e1 = j.write_pending("P001", "OPP001", "deadbeef")
        e2 = j.write_pending("P001", "OPP001", "deadbeef")  # same
        assert e1.envelope_sha256 == e2.envelope_sha256
        # File should have exactly 1 line (no duplicates)
        lines = [l for l in journal_path.read_bytes().splitlines() if l.strip()]
        assert len(lines) == 1

    def test_duplicate_same_id_different_digest_raises(self, tmp_path):
        """C2: same id + different digest → C2ConflictError STOP."""
        journal_path = tmp_path / "journal.jsonl"
        j = DurableJournal(journal_path)
        j.write_pending("P001", "OPP001", "deadbeef")
        with pytest.raises(C2ConflictError):
            j.write_pending("P001", "OPP001", "cafebabe")  # different digest

    def test_restart_journal_loads_existing_state(self, tmp_path):
        """C2: after write_pending + transition_applied, new DurableJournal
        on same path reads the file back and shows correct state.
        """
        journal_path = tmp_path / "journal.jsonl"
        # Session 1: write pending
        j1 = DurableJournal(journal_path)
        j1.write_pending("P001", "OPP001", "aabbccdd")
        j1.transition_applied("P001")

        # Simulate crash: create new process object from same file
        j2 = DurableJournal(journal_path)
        assert "P001" in j2._entries
        entry = j2._entries["P001"]
        assert entry.state == "APPLIED"

    def test_transition_applied_readback_verifies(self, tmp_path):
        """C2: transition_applied does fsync + readback before setting in-memory state."""
        journal_path = tmp_path / "journal.jsonl"
        j = DurableJournal(journal_path)
        j.write_pending("P001", "OPP001", "aabbccdd")
        j.transition_applied("P001")
        # After transition, must be APPLIED in memory
        assert j._entries["P001"].state == "APPLIED"

    def test_transition_acked(self, tmp_path):
        """C2: transition_acked sets ACKED in file and memory."""
        journal_path = tmp_path / "journal.jsonl"
        j = DurableJournal(journal_path)
        j.write_pending("P001", "OPP001", "aabbccdd")
        j.transition_applied("P001")
        count = j.transition_acked(["P001"])
        assert count == 1
        # Reload and verify
        j2 = DurableJournal(journal_path)
        assert j2._entries["P001"].state == "ACKED"


# ===========================================================================
# F3 ADVERSARIAL TESTS
# ===========================================================================

def _make_synthetic_bars(n: int, base_price: float = 42000.0) -> list[P0Bar]:
    """Build n synthetic P0Bars on INTERVAL_MS grid starting at WINDOW_START_MS."""
    bars = []
    for i in range(n):
        open_ms = WINDOW_START_MS + i * BAR_DURATION_MS
        price = base_price + i * 10
        bars.append(P0Bar(
            bar_id=f"BAR-{i:04d}",
            bar_open_ms=open_ms,
            bar_close_ms=open_ms + BAR_DURATION_MS - 1,
            open=price,
            high=price * 1.001,
            low=price * 0.999,
            close=price,
            volume=1.0,
            is_final=True,
            source_label="SYNTHETIC",
            availability_kind="RETROSPECTIVE",
            available_as_of_decision=None,
            observation_lower_bound_ms=open_ms + BAR_DURATION_MS,
            receipt_ms=None,
            known_at_ms=None,
            bar_checksum=_sha256_hex(str(i).encode()),
            gap_state="NO_GAP",
            correction_generation_id="UNKNOWN_NOT_ATTESTED",
            correction_parent_id=None,
        ))
    return bars


def _make_manifest_from_bars(bars: list[P0Bar]) -> P0SourceManifest:
    from research_wp_r0.aql_p0_c1_source import WINDOW_END_EXCLUSIVE_MS, INTERVAL_MS
    synthetic_sha = _sha256_hex(b"synthetic")
    return P0SourceManifest(
        schema="aql.p0.source-manifest.v1",
        project_id="AQL-CRYPTO-RESEARCH-001",
        exchange="BINANCE",
        market="SPOT",
        symbol="BTCUSDT",
        interval_ms=INTERVAL_MS,
        timezone="UTC",
        dataset_id="TEST",
        dataset_version=1,
        raw_generation_id="P0-DEV-2024-01-01-TO-2024-01-08",
        source_bytes_sha256=synthetic_sha,
        source_provider="SYNTHETIC",
        source_version="0",
        source_receipt_sha256=synthetic_sha,
        receipt_status="MISSING_UNATTESTED",
        receipt_missing_reason="SYNTHETIC_TEST_DATA",
        custody_status="LOCAL_VERIFIED_NON_INDEPENDENT",
        manifest_integrity_sha256=synthetic_sha,
        ordered_bar_checksums_sha256=synthetic_sha,
        gap_inventory_sha256=synthetic_sha,
        correction_lineage_sha256=synthetic_sha,
        window_start_ms=WINDOW_START_MS,
        window_end_exclusive_ms=WINDOW_START_MS + len(bars) * INTERVAL_MS,
        mode="RETROSPECTIVE_NON_PIT",
        research_only=True,
        bars=bars,
    )


def _make_opp(opportunity_id: str, signal_idx: int, bars: list[P0Bar]) -> Opportunity:
    """Construct a synthetic ARMED opportunity at bars[signal_idx].
    decision_cutoff_ms = signal_bar.bar_close_ms + 1 = bar[signal_idx+1].bar_open_ms
    decision_ms = decision_cutoff_ms + 2000
    trigger_bar_open_ms = decision_cutoff_ms (the OLD wrong value = bar[signal_idx+1])
    """
    signal_bar = bars[signal_idx]
    decision_cutoff_ms = signal_bar.bar_close_ms + 1
    decision_ms = decision_cutoff_ms + 2000
    trigger_bar_open_ms = bars[signal_idx + 1].bar_open_ms if signal_idx + 1 < len(bars) else None
    prefix_start = bars[max(0, signal_idx - 10)].bar_open_ms
    return Opportunity(
        opportunity_id=opportunity_id,
        producer_event_id=f"PE-{opportunity_id}",
        decision_cutoff_ms=decision_cutoff_ms,
        decision_ms=decision_ms,
        prefix_start_ms=prefix_start,
        prefix_end_exclusive_ms=decision_cutoff_ms,
        prefix_bar_checksums_sha256=_sha256_hex(b"synthetic"),
        input_disposition="ARMED",
        signal_state=SignalState.ARMED,
        reason_code=None,
        entry_level=signal_bar.close,
        exit_level=signal_bar.low,
        trigger_bar_open_ms=trigger_bar_open_ms,
        trigger_bar_close=signal_bar.close,
        prefix_bar_count=min(signal_idx, 10),
        strategy_id="TEST-STRAT",
        trial_id="TEST-TRIAL",
        dataset_version=1,
    )


class TestF3EntryTimingBlocker:
    """F3-ENTRY-CUTOFF: entry_bar.bar_open_ms must be > decision_ms."""

    def test_entry_bar_open_strictly_after_decision_ms(self):
        """FAIL on baseline: trigger_bar_open_ms = cutoff < decision_ms by 2000ms.
        Fix: first bar with open_ms > decision_ms is used.
        """
        bars = _make_synthetic_bars(EXPECTED_BAR_COUNT)
        manifest = _make_manifest_from_bars(bars)

        signal_idx = 15  # far enough from start for context
        opp = _make_opp("OPP-001", signal_idx, bars)
        assert opp.signal_state == SignalState.ARMED

        results = model_fills(manifest, [opp])
        assert len(results) == 1
        r = results[0]

        if r.signal_state in ("TRIGGERED", "OPEN_UNRESOLVED"):
            # CRITICAL: entry bar open_ms must be STRICTLY > decision_ms
            assert r.entry_bar_open_ms is not None
            assert r.entry_bar_open_ms > opp.decision_ms, (
                f"CAUSALITY VIOLATION: entry_bar_open_ms={r.entry_bar_open_ms} "
                f"<= decision_ms={opp.decision_ms}"
            )

    def test_entry_bar_not_equal_to_trigger_bar_open_ms(self):
        """trigger_bar_open_ms (= cutoff) must NOT be used as entry bar when
        trigger_bar_open_ms < decision_ms (which is always true with 2s lag).
        """
        bars = _make_synthetic_bars(EXPECTED_BAR_COUNT)
        manifest = _make_manifest_from_bars(bars)
        signal_idx = 20
        opp = _make_opp("OPP-002", signal_idx, bars)

        results = model_fills(manifest, [opp])
        r = results[0]

        if r.entry_bar_open_ms is not None:
            # trigger_bar_open_ms = decision_cutoff_ms < decision_ms
            # so entry bar MUST NOT equal trigger_bar_open_ms
            assert r.entry_bar_open_ms != opp.trigger_bar_open_ms, (
                f"ENTRY_CUTOFF_VIOLATION: used trigger_bar_open_ms={opp.trigger_bar_open_ms} "
                f"which < decision_ms={opp.decision_ms}"
            )


class TestF3EventTimeStateBlocker:
    """F3-EVENT-TIME: position held until exit_execution_ms passes in event-time."""

    def test_position_held_during_pending_exit(self):
        """FAIL on baseline: position released immediately when exit scanned.
        Fix: next ARMED opportunity at entry_bar.open_ms <= held_until_ms → REJECTED.
        """
        # Need bars where:
        # Opp A enters at bar[N+2], exit signal at bar[N+K], exit exec at bar[N+K+1]
        # Opp B ARMED at bar[M] where bar[M].open_ms <= bar[N+K+1]
        # → Opp B should be REJECTED(POSITION_ALREADY_OPEN)
        bars = _make_synthetic_bars(EXPECTED_BAR_COUNT)
        manifest = _make_manifest_from_bars(bars)

        # Opp A: signal at bar 10
        opp_a = _make_opp("OPP-A", 10, bars)

        # Opp B: signal at bar 12 — its entry bar would be bar[14] (roughly)
        # which is likely BEFORE the exit execution of opp_a
        opp_b = _make_opp("OPP-B", 12, bars)

        results = model_fills(manifest, [opp_a, opp_b])
        assert len(results) == 2
        r_a = results[0]
        r_b = results[1]

        # r_a should have entered
        assert r_a.signal_state in ("TRIGGERED", "OPEN_UNRESOLVED", "NO_FILL")
        if r_a.signal_state in ("TRIGGERED", "OPEN_UNRESOLVED"):
            # r_b should be REJECTED since position is still open
            assert r_b.signal_state == "REJECTED", (
                f"EVENT_TIME_VIOLATION: r_b.signal_state={r_b.signal_state!r} "
                f"but position from r_a was still active at r_b entry bar"
            )

    def test_position_released_after_exit_execution_ms(self):
        """After exit_execution_ms passes in event-time, position IS released."""
        bars = _make_synthetic_bars(EXPECTED_BAR_COUNT)
        manifest = _make_manifest_from_bars(bars)

        # Opp A: early signal
        opp_a = _make_opp("OPP-A", 11, bars)
        # Opp B: very late signal — entry bar should be well after any exit exec
        opp_b = _make_opp("OPP-B", EXPECTED_BAR_COUNT - 5, bars)

        # This second opp has extremely late entry bar
        # If opp_a TRIGGERED and exit happened well before opp_b's entry bar,
        # then opp_b should NOT be REJECTED
        results = model_fills(manifest, [opp_a, opp_b])
        r_a = results[0]
        r_b = results[1]

        if r_a.signal_state == "TRIGGERED" and r_b.entry_bar_open_ms is not None:
            if r_a.exit_bar_open_ms is not None:
                if r_b.entry_bar_open_ms > r_a.exit_bar_open_ms:
                    # Position was released before opp_b's entry — should not be REJECTED
                    assert r_b.signal_state != "REJECTED" or r_b.reason_code != "POSITION_ALREADY_OPEN", (
                        f"EVENT_TIME_VIOLATION: position should be released by "
                        f"opp_b entry={r_b.entry_bar_open_ms} > "
                        f"exit_exec={r_a.exit_bar_open_ms}"
                    )

    def test_event_time_explicit_t5_entry_equals_exit_exec(self):
        """F3-EVENT-TIME-GTE: OPP-B entry bar open_ms == OPP-A exit exec bar open_ms.

        EVIDENCE_CLASS: SYNTHETIC_ONLY
        (Controlled price pattern with explicit bar indices; proves the >= fix is active.)

        Scenario:
          bars 15-24: price=43000, low≈42957 (= 43000 * 0.999)
          bar  25:    close=41000 (< 42957 → exit signal for OPP-A, exec at bar 26)
          OPP-A: signal at bar 10, entry at bar 12, exit exec at bar 26.
          OPP-B: signal at bar 24, entry bar = bar 26 (= OPP-A's exit exec bar).
          held_until_ms = bar[26].bar_open_ms

        With >= fix (this code): entry_bar.open_ms >= held_until_ms → RELEASE position → OPP-B NOT rejected.
        With old >  (baseline):  entry_bar.open_ms >  held_until_ms → FALSE (equal) → OPP-B REJECTED.
        """
        n = 50
        custom_bars = []
        for i in range(n):
            open_ms = WINDOW_START_MS + i * BAR_DURATION_MS
            if 15 <= i <= 24:
                price = 43000.0
                low_val = 43000.0 * 0.999   # ≈ 42957 — the exit level
                close_val = price
            elif i == 25:
                price = 43000.0
                low_val = 40500.0
                close_val = 41000.0          # < 42957 → exit signal fires here
            else:
                price = 42000.0
                low_val = 42000.0 * 0.999
                close_val = price
            custom_bars.append(P0Bar(
                bar_id=f"BAR-{i:04d}",
                bar_open_ms=open_ms,
                bar_close_ms=open_ms + BAR_DURATION_MS - 1,
                open=price,
                high=price * 1.001,
                low=low_val,
                close=close_val,
                volume=1.0,
                is_final=True,
                source_label="SYNTHETIC",
                availability_kind="RETROSPECTIVE",
                available_as_of_decision=None,
                observation_lower_bound_ms=open_ms + BAR_DURATION_MS,
                receipt_ms=None,
                known_at_ms=None,
                bar_checksum=_sha256_hex(str(i).encode()),
                gap_state="NO_GAP",
                correction_generation_id="UNKNOWN_NOT_ATTESTED",
                correction_parent_id=None,
            ))

        manifest = _make_manifest_from_bars(custom_bars)
        opp_a = _make_opp("OPP-A", 10, custom_bars)
        opp_b = _make_opp("OPP-B", 24, custom_bars)

        results = model_fills(manifest, [opp_a, opp_b])
        assert len(results) == 2
        r_a, r_b = results

        # OPP-A must TRIGGER with exit execution at bar 26
        assert r_a.signal_state == "TRIGGERED", (
            f"Expected OPP-A TRIGGERED, got {r_a.signal_state!r} "
            f"(reason: {r_a.reason_code!r})"
        )
        bar26_open_ms = WINDOW_START_MS + 26 * BAR_DURATION_MS
        assert r_a.exit_bar_open_ms == bar26_open_ms, (
            f"Expected OPP-A exit exec at bar 26 (open_ms={bar26_open_ms}), "
            f"got {r_a.exit_bar_open_ms!r}"
        )

        # OPP-B's entry bar = bar 26 (same open_ms as held_until_ms).
        # >= fix: position RELEASED → OPP-B must NOT be POSITION_ALREADY_OPEN.
        assert not (r_b.signal_state == "REJECTED" and r_b.reason_code == "POSITION_ALREADY_OPEN"), (
            f"F3_GTE_BUG DETECTED: OPP-B rejected with POSITION_ALREADY_OPEN "
            f"despite entry_bar.open_ms == held_until_ms={bar26_open_ms}. "
            f"The >= fix is not active."
        )


# ===========================================================================
# F4 ADVERSARIAL TESTS
# ===========================================================================

class TestF4DurableReceiptsBlocker:
    """F4: report_sha256 must cover individual event hashes, not just aggregates."""

    def _make_triggered_fill(
        self,
        opportunity_id: str,
        entry_bar_open_ms: int,
        exit_bar_open_ms: int,
        entry_price: float = 42000.0,
        exit_price: float = 43000.0,
    ) -> FillResult:
        from research_wp_r0.aql_p0_f3_fill_model import _entry_net, _exit_net, _net_return
        entry_net_p, entry_fee = _entry_net(entry_price)
        exit_net_p, exit_fee = _exit_net(exit_price)
        gross, net = _net_return(entry_net_p, exit_net_p, entry_fee, exit_fee)
        return FillResult(
            opportunity_id=opportunity_id,
            signal_state="TRIGGERED",
            reason_code=None,
            entry_bar_open_ms=entry_bar_open_ms,
            entry_price_gross=Decimal(str(entry_price)),
            entry_price_net=entry_net_p,
            entry_fee=entry_fee,
            exit_bar_open_ms=exit_bar_open_ms,
            exit_price_gross=Decimal(str(exit_price)),
            exit_price_net=exit_net_p,
            exit_fee=exit_fee,
            gross_return=gross,
            net_return=net,
            is_terminal=True,
        )

    def _make_opp_stub(self, opportunity_id: str) -> Opportunity:
        t = WINDOW_START_MS
        cutoff = t + BAR_DURATION_MS
        return Opportunity(
            opportunity_id=opportunity_id,
            producer_event_id=f"PE-{opportunity_id}",
            decision_cutoff_ms=cutoff,
            decision_ms=cutoff + 2000,
            prefix_start_ms=t,
            prefix_end_exclusive_ms=cutoff,
            prefix_bar_checksums_sha256=_sha256_hex(b"synthetic"),
            input_disposition="ARMED",
            signal_state=SignalState.ARMED,
            reason_code=None,
            entry_level=42000.0,
            exit_level=41000.0,
            trigger_bar_open_ms=cutoff,
            trigger_bar_close=42000.0,
            prefix_bar_count=1,
            strategy_id="TEST-STRAT",
            trial_id="TEST-TRIAL",
            dataset_version=1,
        )

    def test_altering_event_price_changes_report_hash(self):
        """FAIL on baseline: report_sha256 only covers aggregates.
        Fix: changing any event's price changes ordered_receipt_hashes → different digest.
        """
        opp = self._make_opp_stub("OPP-001")

        fill_v1 = self._make_triggered_fill(
            "OPP-001",
            entry_bar_open_ms=WINDOW_START_MS + 2 * BAR_DURATION_MS,
            exit_bar_open_ms=WINDOW_START_MS + 5 * BAR_DURATION_MS,
            entry_price=42000.0,
            exit_price=43000.0,
        )
        fill_v2 = self._make_triggered_fill(
            "OPP-001",
            entry_bar_open_ms=WINDOW_START_MS + 2 * BAR_DURATION_MS,
            exit_bar_open_ms=WINDOW_START_MS + 5 * BAR_DURATION_MS,
            entry_price=42000.0,
            exit_price=44000.0,  # different exit price → different event → different hash
        )

        _, report_v1 = build_ledger([opp], [fill_v1], trial_id="T001")
        _, report_v2 = build_ledger([opp], [fill_v2], trial_id="T001")

        # Different event payload → different report_sha256
        assert report_v1.report_sha256() != report_v2.report_sha256(), (
            "F4_AGGREGATE_ONLY_HASH: report_sha256 did not change when event "
            "price was altered — tamper detection failed"
        )

    def test_tamper_preserve_totals_different_hash(self):
        """Key F4 adversarial case: alter one event while preserving aggregate cash.
        Pre-fix: same digest (aggregate only). Post-fix: different digest (receipt hashes).
        """
        opp1 = self._make_opp_stub("OPP-001")
        cutoff2 = WINDOW_START_MS + 11 * BAR_DURATION_MS
        opp2 = Opportunity(
            opportunity_id="OPP-002",
            producer_event_id="PE-OPP-002",
            decision_cutoff_ms=cutoff2,
            decision_ms=cutoff2 + 2000,
            prefix_start_ms=WINDOW_START_MS + 10 * BAR_DURATION_MS,
            prefix_end_exclusive_ms=cutoff2,
            prefix_bar_checksums_sha256=_sha256_hex(b"synthetic2"),
            input_disposition="ARMED",
            signal_state=SignalState.ARMED,
            reason_code=None,
            entry_level=44000.0,
            exit_level=43000.0,
            trigger_bar_open_ms=cutoff2,
            trigger_bar_close=44000.0,
            prefix_bar_count=1,
            strategy_id="TEST-STRAT",
            trial_id="TEST-TRIAL",
            dataset_version=1,
        )

        # Two fills, same net aggregate but different individual prices
        fill1a = self._make_triggered_fill("OPP-001",
            WINDOW_START_MS + 2 * BAR_DURATION_MS,
            WINDOW_START_MS + 4 * BAR_DURATION_MS,
            entry_price=42000.0, exit_price=43000.0)
        fill2a = self._make_triggered_fill("OPP-002",
            WINDOW_START_MS + 12 * BAR_DURATION_MS,
            WINDOW_START_MS + 14 * BAR_DURATION_MS,
            entry_price=44000.0, exit_price=45000.0)

        # Swapped prices (same net aggregate sum if the numbers happen to cancel)
        fill1b = self._make_triggered_fill("OPP-001",
            WINDOW_START_MS + 2 * BAR_DURATION_MS,
            WINDOW_START_MS + 4 * BAR_DURATION_MS,
            entry_price=42000.0, exit_price=45000.0)  # higher exit
        fill2b = self._make_triggered_fill("OPP-002",
            WINDOW_START_MS + 12 * BAR_DURATION_MS,
            WINDOW_START_MS + 14 * BAR_DURATION_MS,
            entry_price=44000.0, exit_price=43000.0)  # lower exit

        state_a, report_a = build_ledger([opp1, opp2], [fill1a, fill2a], trial_id="T002")
        state_b, report_b = build_ledger([opp1, opp2], [fill1b, fill2b], trial_id="T002")

        # Individual events differ → ordered_receipt_hashes differ → different report_sha256
        assert report_a.ordered_receipt_hashes != report_b.ordered_receipt_hashes
        assert report_a.report_sha256() != report_b.report_sha256(), (
            "F4_TAMPER_DETECTION_FAILED: different events produced same report_sha256"
        )

    def test_persist_receipts_fsync_and_reload(self, tmp_path):
        """F4: persist_receipts writes JSON-lines + fsync; load_receipts reads back."""
        opp = self._make_opp_stub("OPP-001")
        fill = self._make_triggered_fill("OPP-001",
            WINDOW_START_MS + 2 * BAR_DURATION_MS,
            WINDOW_START_MS + 5 * BAR_DURATION_MS)

        state, report = build_ledger([opp], [fill], trial_id="T001")

        receipt_path = tmp_path / "receipts.jsonl"
        written = persist_receipts(state, receipt_path)
        assert written > 0
        assert receipt_path.exists()

        # Reload and verify
        loaded = load_receipts(receipt_path)
        assert len(loaded) == written
        # All event_ids in state._receipts should be in loaded
        for r in getattr(state, "_receipts", []):
            assert r.event_id in loaded
            assert loaded[r.event_id] == r.payload_hash

    def test_persist_receipts_idempotent(self, tmp_path):
        """F4: calling persist_receipts twice with same state → second call writes 0."""
        opp = self._make_opp_stub("OPP-001")
        fill = self._make_triggered_fill("OPP-001",
            WINDOW_START_MS + 2 * BAR_DURATION_MS,
            WINDOW_START_MS + 5 * BAR_DURATION_MS)

        state, _ = build_ledger([opp], [fill], trial_id="T001")
        receipt_path = tmp_path / "receipts.jsonl"

        written1 = persist_receipts(state, receipt_path)
        written2 = persist_receipts(state, receipt_path)  # same state, already persisted
        assert written1 > 0
        assert written2 == 0  # idempotent

    def test_corrupted_receipt_different_payload_raises(self, tmp_path):
        """F4: same event_id + different payload_hash in receipt file → STOP."""
        opp = self._make_opp_stub("OPP-001")
        fill = self._make_triggered_fill("OPP-001",
            WINDOW_START_MS + 2 * BAR_DURATION_MS,
            WINDOW_START_MS + 5 * BAR_DURATION_MS)

        state, _ = build_ledger([opp], [fill], trial_id="T001")
        receipt_path = tmp_path / "receipts.jsonl"
        persist_receipts(state, receipt_path)

        # Tamper: overwrite payload_hash in file
        lines = receipt_path.read_bytes().splitlines()
        tampered_lines = []
        for line in lines:
            d = json.loads(line)
            d["payload_hash"] = "0" * 64  # wrong hash
            tampered_lines.append(json.dumps(d, sort_keys=True).encode())
        receipt_path.write_bytes(b"\n".join(tampered_lines) + b"\n")

        # Now reconcile: should detect conflict
        loaded = load_receipts(receipt_path)
        with pytest.raises(LedgerReceiptCorrupted, match="RECONCILE_CONFLICT"):
            reconcile_receipts(state, loaded)

    def test_report_sha256_covers_receipts_field(self):
        """report_sha256 must include ordered_receipt_hashes."""
        opp = self._make_opp_stub("OPP-001")
        fill = self._make_triggered_fill("OPP-001",
            WINDOW_START_MS + 2 * BAR_DURATION_MS,
            WINDOW_START_MS + 5 * BAR_DURATION_MS)

        _, report = build_ledger([opp], [fill], trial_id="T001")
        assert len(report.ordered_receipt_hashes) > 0, (
            "F4: ordered_receipt_hashes is empty — receipts not computed"
        )

    def test_persist_and_load_report_round_trip(self, tmp_path):
        """F4: persist_report writes and load_report reads back with same hash."""
        opp = self._make_opp_stub("OPP-001")
        fill = self._make_triggered_fill("OPP-001",
            WINDOW_START_MS + 2 * BAR_DURATION_MS,
            WINDOW_START_MS + 5 * BAR_DURATION_MS)

        state, report = build_ledger([opp], [fill], trial_id="T001")
        report_path = tmp_path / "report.json"
        written_sha = persist_report(report, report_path, state)

        loaded = load_report(report_path)
        assert loaded.report_sha256() == written_sha
        assert loaded.ordered_receipt_hashes == report.ordered_receipt_hashes

    def test_new_process_restart_reconciles_no_double_effect(self, tmp_path):
        """F4: REAL_PROCESS_BOUNDARY — subprocess proves cross-process crash recovery.

        EVIDENCE_CLASS: REAL_PROCESS_BOUNDARY
        (Uses subprocess.run() so the restart truly crosses a process boundary;
        not just two objects in the same process.)

        Scenario: process 1 builds ledger + persists receipts, then "crashes" before
        persist_report. Process 2 (subprocess) reloads receipts, rebuilds from the
        same inputs, reconciles, and asserts no double-effect (written == 0).
        """
        opp = self._make_opp_stub("OPP-001")
        fill = self._make_triggered_fill("OPP-001",
            WINDOW_START_MS + 2 * BAR_DURATION_MS,
            WINDOW_START_MS + 5 * BAR_DURATION_MS)

        # Process 1: build + persist receipts (crash before persist_report)
        state1, _ = build_ledger([opp], [fill], trial_id="T001")
        receipt_path = tmp_path / "receipts.jsonl"
        persist_receipts(state1, receipt_path)

        # REAL_PROCESS_BOUNDARY: subprocess is the "restarted process"
        subprocess_script = f"""
import sys
sys.path.insert(0, {str(REPO_ROOT)!r})
from pathlib import Path
from decimal import Decimal
from research_wp_r0.aql_p0_c1_source import _sha256_hex
from research_wp_r0.aql_p0_f1f2_opportunities import Opportunity, SignalState
from research_wp_r0.aql_p0_f3_fill_model import FillResult, _entry_net, _exit_net, _net_return
from research_wp_r0.aql_p0_f4_ledger import (
    build_ledger, persist_receipts, load_receipts, reconcile_receipts
)

WINDOW_START_MS = {WINDOW_START_MS}
BAR_DURATION_MS = {BAR_DURATION_MS}
receipt_path = Path({str(receipt_path)!r})

cutoff = WINDOW_START_MS + BAR_DURATION_MS
opp = Opportunity(
    opportunity_id="OPP-001",
    producer_event_id="PE-OPP-001",
    decision_cutoff_ms=cutoff,
    decision_ms=cutoff + 2000,
    prefix_start_ms=WINDOW_START_MS,
    prefix_end_exclusive_ms=cutoff,
    prefix_bar_checksums_sha256=_sha256_hex(b"synthetic"),
    input_disposition="ARMED",
    signal_state=SignalState.ARMED,
    reason_code=None,
    entry_level=42000.0,
    exit_level=41000.0,
    trigger_bar_open_ms=cutoff,
    trigger_bar_close=42000.0,
    prefix_bar_count=1,
    strategy_id="TEST-STRAT",
    trial_id="TEST-TRIAL",
    dataset_version=1,
)
entry_net_p, entry_fee = _entry_net(42000.0)
exit_net_p, exit_fee = _exit_net(43000.0)
gross, net = _net_return(entry_net_p, exit_net_p, entry_fee, exit_fee)
fill = FillResult(
    opportunity_id="OPP-001",
    signal_state="TRIGGERED",
    reason_code=None,
    entry_bar_open_ms=WINDOW_START_MS + 2 * BAR_DURATION_MS,
    entry_price_gross=Decimal("42000.0"),
    entry_price_net=entry_net_p,
    entry_fee=entry_fee,
    exit_bar_open_ms=WINDOW_START_MS + 5 * BAR_DURATION_MS,
    exit_price_gross=Decimal("43000.0"),
    exit_price_net=exit_net_p,
    exit_fee=exit_fee,
    gross_return=gross,
    net_return=net,
    is_terminal=True,
)

# Restarted process: load persisted receipts, rebuild, reconcile
persisted = load_receipts(receipt_path)
state2, _ = build_ledger([opp], [fill], trial_id="T001")
reconcile_receipts(state2, persisted)   # must not raise

# Re-persist: must write 0 new lines (no double-effect)
written = persist_receipts(state2, receipt_path)
assert written == 0, f"DOUBLE_EFFECT: persist_receipts wrote {{written}} lines after restart"
print("SUBPROCESS_PASS: no double-effect after cross-process restart")
"""
        result = subprocess.run(
            [sys.executable, "-c", subprocess_script],
            capture_output=True, text=True, timeout=30,
        )
        assert result.returncode == 0, (
            f"SUBPROCESS_FAILED (returncode={result.returncode}):\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}"
        )
        assert "SUBPROCESS_PASS" in result.stdout, (
            f"SUBPROCESS_PASS sentinel missing from stdout:\n{result.stdout!r}"
        )
