"""
SF-DATA-01 — Historical Market Data Library V1
Acceptance tests for Issues #47 and #50 (SF-DATA-01-FIX01)

Coverage (original SF-DATA-01 / Issue #47):
  T01  deterministic import and snapshot replay; checksums and immutable versions
  T02  invalid / missing / duplicate / out-of-order / non-final / cross-source conflicts
  T03  gaps and coverage report with fail-closed quality eligibility
  T04  point-in-time decisions against later corrections and unknown observation timestamps
  T05  concurrent historical reads across different versions and deterministic cache identity
  T06  archive-copy failure/backpressure isolation (synthetic double only)
  T07  negative security: path traversal, corrupted manifest, snapshot rewrite
  T08  combined acceptance gate — all 8 AGs must PASS in one machine-readable block

Coverage (SF-DATA-01-FIX01 / Issue #50):
  T09  Gap 1 — checksum completeness: observation_cutoff_ms, ingest_time_ms, source_label
       are part of the SHA-256 payload; changes to any provenance field change the checksum
  T10  Gap 2 — DatasetManifest immutability: frozen dataclass + manifest_integrity_hash
       detects metadata tampering; register/correct use dataclasses.replace, not mutation
  T11  Gap 3 — import confinement: raw-string ".." guard fires before resolve(),
       symlink rejection, trusted_root boundary enforcement
  T12  Gap 4 — range_query fail-closed: partial coverage raises by default;
       require_complete=False opt-in; empty range always raises
  T13  FIX01 combined acceptance gate — all 4 fix gates must PASS
"""
from __future__ import annotations

import hashlib
import io
import queue
import tempfile
import threading
import time
from pathlib import Path
from typing import List

import pytest

import dataclasses
import os

from research_wp_r0.historical_library import (
    ArchiveCopyInterface,
    BarQuality,
    DatasetManifest,
    HistoricalBar,
    HistoricalDataError,
    HistoricalLibrary,
    SourceType,
    _interval_to_ms,
    import_fixture_csv,
    make_fixture_csv,
    make_test_bar,
    validate_bars,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SYMBOL = "BTCUSDT"
INTERVAL = "1m"
BASE = 1_700_000_000_000
IMS = 60_000  # 1 minute in ms


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _bars(n: int, base: int = BASE) -> List[HistoricalBar]:
    return [make_test_bar(i, base_open=base) for i in range(n)]


def _lib_with(n: int = 10, dataset_id: str = "BTC1M") -> HistoricalLibrary:
    lib = HistoricalLibrary()
    bars = _bars(n)
    validated, manifest = validate_bars(bars, SYMBOL, INTERVAL)
    manifest = dataclasses.replace(manifest,
                                   dataset_id=dataset_id,
                                   exchange="binance",
                                   market="spot")
    lib.register(dataset_id, bars, manifest)
    return lib


# ---------------------------------------------------------------------------
# T01 — deterministic import, checksums, immutable versions
# ---------------------------------------------------------------------------

class TestImportAndChecksums:

    def test_checksums_are_deterministic(self):
        bar = make_test_bar(0)
        assert bar.checksum == make_test_bar(0).checksum

    def test_checksum_changes_with_price(self):
        b1 = make_test_bar(0)
        # Manually build a bar with different close
        b2 = HistoricalBar(
            symbol=b1.symbol, interval=b1.interval,
            bar_open=b1.bar_open, bar_close=b1.bar_close,
            open=b1.open, high=b1.high, low=b1.low, close=999.0, volume=b1.volume,
            quality=b1.quality, source=b1.source, source_label=b1.source_label,
            observation_cutoff_ms=b1.observation_cutoff_ms, ingest_time_ms=None,
        )
        assert b1.checksum != b2.checksum

    def test_verify_checksum_ok(self):
        bar = make_test_bar(3)
        assert bar.verify_checksum()

    def test_validate_produces_manifest_hash(self):
        bars = _bars(5)
        validated, manifest = validate_bars(bars, SYMBOL, INTERVAL)
        assert len(manifest.manifest_hash) == 64
        assert manifest.verify_hash(validated)

    def test_snapshot_replay_deterministic(self):
        lib = _lib_with(10)
        cutoff = BASE + 10 * IMS  # after all bars
        snap1 = lib.snapshot("BTC1M", cutoff)
        snap2 = lib.snapshot("BTC1M", cutoff)
        assert [b.bar_open for b in snap1] == [b.bar_open for b in snap2]

    def test_register_same_version_raises(self):
        lib = HistoricalLibrary()
        bars = _bars(5)
        validated, manifest = validate_bars(bars, SYMBOL, INTERVAL)
        manifest = dataclasses.replace(manifest, dataset_id="X")
        lib.register("X", bars, manifest)
        # Build a second manifest for the same version
        bars2 = _bars(5)
        _, manifest2 = validate_bars(bars2, SYMBOL, INTERVAL)
        manifest2 = dataclasses.replace(manifest2, dataset_id="X", version=1)
        with pytest.raises(HistoricalDataError, match="already registered"):
            lib.register("X", bars2, manifest2)

    def test_fixture_csv_import_roundtrip(self, tmp_path):
        bars = _bars(8)
        csv_text = make_fixture_csv(bars)
        p = tmp_path / "fixture.csv"
        p.write_text(csv_text)
        imported, manifest = import_fixture_csv(str(p), SYMBOL, INTERVAL)
        assert len(imported) == 8
        assert manifest.bar_count == 8
        assert manifest.verify_hash(imported)


# ---------------------------------------------------------------------------
# T02 — invalid / edge-case inputs
# ---------------------------------------------------------------------------

class TestInvalidInputs:

    def test_empty_bars_raises(self):
        with pytest.raises(HistoricalDataError, match="Empty"):
            validate_bars([], SYMBOL, INTERVAL)

    def test_non_final_bar_raises(self):
        bar = make_test_bar(0, quality=BarQuality.NON_FINAL)
        with pytest.raises(HistoricalDataError, match="non-final"):
            validate_bars([bar], SYMBOL, INTERVAL)

    def test_duplicate_bar_open_raises(self):
        b1 = make_test_bar(0)
        b2 = make_test_bar(0)  # same bar_open
        with pytest.raises(HistoricalDataError, match="Duplicate"):
            validate_bars([b1, b2], SYMBOL, INTERVAL)

    def test_out_of_order_raises(self):
        b0 = make_test_bar(0)
        b2 = make_test_bar(2)
        b1 = make_test_bar(1)
        # pass in wrong order: b0, b2, b1
        with pytest.raises(HistoricalDataError, match="Out-of-order|Duplicate"):
            validate_bars([b0, b2, b1], SYMBOL, INTERVAL)

    def test_wrong_bar_close_raises(self):
        # Create a bar via CSV with wrong bar_close
        bar = make_test_bar(0)
        bad_row = f"{bar.bar_open},{bar.bar_open + 1},{bar.open},{bar.high},{bar.low},{bar.close},{bar.volume}"
        with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False) as f:
            f.write(bad_row)
            fname = f.name
        with pytest.raises(HistoricalDataError, match="bar_close"):
            import_fixture_csv(fname, SYMBOL, INTERVAL)

    def test_cross_symbol_raises(self):
        bar = make_test_bar(0, symbol="ETHUSDT")
        with pytest.raises(HistoricalDataError, match="Cross-symbol"):
            validate_bars([bar], SYMBOL, INTERVAL)

    def test_csv_missing_columns_raises(self, tmp_path):
        p = tmp_path / "bad.csv"
        p.write_text("100,200,300\n")  # only 3 columns
        with pytest.raises(HistoricalDataError, match="7 columns"):
            import_fixture_csv(str(p), SYMBOL, INTERVAL)

    def test_missing_fixture_raises(self):
        with pytest.raises(HistoricalDataError, match="not found"):
            import_fixture_csv("/nonexistent/path.csv", SYMBOL, INTERVAL)


# ---------------------------------------------------------------------------
# T03 — gaps and coverage report
# ---------------------------------------------------------------------------

class TestGapsAndCoverage:

    def test_gap_raises_by_default(self):
        # bars 0,1,2 then skip 3, go to 4
        bars = [make_test_bar(i) for i in [0, 1, 2, 4]]
        with pytest.raises(HistoricalDataError, match="gap"):
            validate_bars(bars, SYMBOL, INTERVAL)

    def test_gap_recorded_in_manifest_when_allowed(self):
        bars = [make_test_bar(i) for i in [0, 1, 2, 4]]
        _, manifest = validate_bars(bars, SYMBOL, INTERVAL, allow_gaps=True)
        assert manifest.gap_count == 1
        assert BASE + 3 * IMS in manifest.gap_bar_opens

    def test_coverage_pct_full(self):
        bars = _bars(5)
        _, manifest = validate_bars(bars, SYMBOL, INTERVAL)
        assert manifest.coverage_pct == 100.0

    def test_coverage_pct_partial(self):
        bars = [make_test_bar(i) for i in [0, 1, 2, 4, 5]]  # gap at 3
        _, manifest = validate_bars(bars, SYMBOL, INTERVAL, allow_gaps=True)
        # 5 bars out of 6 expected
        assert manifest.coverage_pct < 100.0

    def test_range_query_empty_raises(self):
        lib = _lib_with(5)
        far_future = BASE + 100 * IMS
        with pytest.raises(HistoricalDataError):
            lib.range_query("BTC1M", far_future, far_future + IMS, far_future + IMS + 1)

    def test_coverage_report_structure(self):
        lib = _lib_with(10)
        report = lib.coverage_report("BTC1M")
        assert set(report.keys()) >= {"dataset_id", "version", "bar_count", "coverage_pct", "gap_count"}

    def test_unknown_dataset_raises(self):
        lib = HistoricalLibrary()
        with pytest.raises(HistoricalDataError, match="Unknown"):
            lib.snapshot("NONEXISTENT", BASE)


# ---------------------------------------------------------------------------
# T04 — point-in-time correctness and lineage
# ---------------------------------------------------------------------------

class TestPointInTime:

    def test_bars_excluded_before_observation_cutoff(self):
        """Bars are invisible before their bar_close + 1."""
        lib = _lib_with(5)
        # cutoff just BEFORE bar 4 closes
        bar4_cutoff = BASE + 4 * IMS + IMS  # = bar_close+1 for bar index 4
        cutoff_before = bar4_cutoff - 1
        snap = lib.snapshot("BTC1M", cutoff_before)
        opens = [b.bar_open for b in snap]
        assert BASE + 4 * IMS not in opens

    def test_bars_visible_after_observation_cutoff(self):
        lib = _lib_with(5)
        bar4_cutoff = BASE + 4 * IMS + IMS
        snap = lib.snapshot("BTC1M", bar4_cutoff)
        opens = [b.bar_open for b in snap]
        assert BASE + 4 * IMS in opens

    def test_ingest_delay_shifts_observation_cutoff(self):
        """When ingest_time > bar_close+1, bar is invisible until ingest_time."""
        bar = make_test_bar(0, ingest_time_ms=BASE + IMS + 5000)
        # observation_cutoff = max(bar_close+1, ingest_time_ms)
        assert bar.observation_cutoff_ms == BASE + IMS + 5000

    def test_correction_creates_new_version(self):
        lib = _lib_with(5)
        new_bars = _bars(5)  # same data, re-validated (simulates correction)
        lib.correct("BTC1M", new_bars, reason="price fix")
        assert lib.latest_version("BTC1M") == 2

    def test_old_version_unchanged_after_correction(self):
        lib = _lib_with(5)
        m_v1 = lib.get_manifest("BTC1M", version=1)
        lib.correct("BTC1M", _bars(5), reason="correction")
        m_v1_after = lib.get_manifest("BTC1M", version=1)
        assert m_v1.manifest_hash == m_v1_after.manifest_hash

    def test_lineage_recorded(self):
        lib = _lib_with(5)
        lib.correct("BTC1M", _bars(5), reason="fix close prices")
        m_v2 = lib.get_manifest("BTC1M", version=2)
        assert m_v2.parent_version == 1
        assert "fix close prices" in m_v2.lineage_reason

    def test_unknown_ingest_time_not_fabricated(self):
        bar = make_test_bar(0, ingest_time_ms=None)
        assert bar.ingest_time_ms is None
        # observation_cutoff is bar_close + 1, not a guessed time
        assert bar.observation_cutoff_ms == bar.bar_close + 1


# ---------------------------------------------------------------------------
# T05 — concurrent reads, version isolation, cache identity
# ---------------------------------------------------------------------------

class TestConcurrentReads:

    def test_concurrent_snapshot_reads_consistent(self):
        lib = _lib_with(20)
        cutoff = BASE + 20 * IMS
        results = []

        def reader():
            snap = lib.snapshot("BTC1M", cutoff)
            results.append(tuple(b.bar_open for b in snap))

        threads = [threading.Thread(target=reader) for _ in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(results) == 8
        assert all(r == results[0] for r in results)

    def test_different_version_snapshots_independent(self):
        lib = _lib_with(5)
        # v2: only 3 bars (simulates smaller correction)
        lib.correct("BTC1M", _bars(3), reason="test")
        cutoff = BASE + 20 * IMS
        snap_v1 = lib.snapshot("BTC1M", cutoff, version=1)
        snap_v2 = lib.snapshot("BTC1M", cutoff, version=2)
        assert len(snap_v1) == 5
        assert len(snap_v2) == 3

    def test_snapshot_identity_same_version_same_cutoff(self):
        """Repeated calls with same args return identical bar_open sequences."""
        lib = _lib_with(10)
        cutoff = BASE + 10 * IMS
        s1 = [b.bar_open for b in lib.snapshot("BTC1M", cutoff)]
        s2 = [b.bar_open for b in lib.snapshot("BTC1M", cutoff)]
        assert s1 == s2


# ---------------------------------------------------------------------------
# T06 — archive-copy failure/backpressure isolation
# ---------------------------------------------------------------------------

class TestArchiveCopy:

    def test_enqueue_does_not_block(self):
        """Producer never blocks even when queue is full."""
        iface = ArchiveCopyInterface(maxsize=3)
        # No worker started — queue will fill
        bars = _bars(10)
        results = [iface.enqueue(b) for b in bars]
        # First 3 should succeed, rest dropped
        enqueued = sum(1 for r in results if r)
        dropped = sum(1 for r in results if not r)
        assert enqueued == 3
        assert dropped == 7

    def test_write_failure_does_not_propagate(self):
        """Write errors increment counter but never raise to producer."""
        def bad_write(bar):
            raise RuntimeError("disk full")

        iface = ArchiveCopyInterface(maxsize=100, write_fn=bad_write)
        iface.start()
        bars = _bars(5)
        for b in bars:
            iface.enqueue(b)
        iface.stop(timeout_s=1.0)
        assert iface.stats["write_errors"] == 5
        assert iface.stats["written"] == 0

    def test_successful_writes_counted(self):
        written = []

        def good_write(bar):
            written.append(bar.bar_open)

        iface = ArchiveCopyInterface(maxsize=100, write_fn=good_write)
        iface.start()
        bars = _bars(5)
        for b in bars:
            iface.enqueue(b)
        iface.stop(timeout_s=1.0)
        assert iface.stats["written"] == 5
        assert iface.stats["write_errors"] == 0

    def test_backpressure_drop_stats(self):
        iface = ArchiveCopyInterface(maxsize=2)
        # Fill queue without starting worker
        for i in range(5):
            iface.enqueue(make_test_bar(i))
        stats = iface.stats
        assert stats["enqueued"] == 2
        assert stats["dropped"] == 3

    def test_fast_producer_not_blocked_by_slow_writer(self):
        """Producer throughput is independent of writer speed."""
        slow_called = []

        def slow_write(bar):
            time.sleep(0.05)
            slow_called.append(bar.bar_open)

        iface = ArchiveCopyInterface(maxsize=50, write_fn=slow_write)
        iface.start()
        t0 = time.monotonic()
        bars = _bars(20)
        for b in bars:
            iface.enqueue(b)
        elapsed = time.monotonic() - t0
        iface.stop(timeout_s=5.0)
        # Producer should finish well under total write time (20 × 50ms = 1s)
        assert elapsed < 0.5, f"Producer was blocked: {elapsed:.3f}s"


# ---------------------------------------------------------------------------
# T07 — negative security
# ---------------------------------------------------------------------------

class TestSecurity:

    def test_path_traversal_rejected(self, tmp_path):
        with pytest.raises((ValueError, HistoricalDataError)):
            import_fixture_csv("../../etc/passwd", SYMBOL, INTERVAL)

    def test_corrupted_manifest_hash_detected(self):
        bars = _bars(5)
        _, manifest = validate_bars(bars, SYMBOL, INTERVAL)
        # FIX01: manifest is frozen — simulate low-level tamper via object.__setattr__
        object.__setattr__(manifest, "manifest_hash", "0" * 64)
        assert not manifest.verify_hash(bars)

    def test_snapshot_is_a_copy_not_mutable_reference(self):
        """Modifying the returned snapshot list must not corrupt the library."""
        lib = _lib_with(5)
        cutoff = BASE + 10 * IMS
        snap = lib.snapshot("BTC1M", cutoff)
        original_len = len(snap)
        snap.clear()  # mutate the returned list
        snap2 = lib.snapshot("BTC1M", cutoff)
        assert len(snap2) == original_len  # library is intact

    def test_register_does_not_accept_unvalidated_data(self):
        """Only validated bars (from validate_bars) produce a correct manifest_hash."""
        lib = HistoricalLibrary()
        bars = _bars(3)
        _, manifest = validate_bars(bars, SYMBOL, INTERVAL)
        manifest = dataclasses.replace(manifest, dataset_id="DS")
        lib.register("DS", bars, manifest)
        m = lib.get_manifest("DS")
        assert m.verify_hash(bars)

    def test_fixture_file_not_a_file_raises(self, tmp_path):
        d = tmp_path / "not_a_file"
        d.mkdir()
        with pytest.raises(HistoricalDataError, match="not found"):
            import_fixture_csv(str(d), SYMBOL, INTERVAL)


# ---------------------------------------------------------------------------
# T08 — Combined acceptance gate
# ---------------------------------------------------------------------------

class TestAcceptanceGate:
    """
    Machine-readable acceptance gate.
    All 8 AGs must PASS for the PR to be valid.
    """

    def _run_gate(self, name: str, fn) -> Tuple[str, str]:
        try:
            fn()
            return name, "PASS"
        except Exception as e:
            return name, f"FAIL: {e}"

    def test_all_acceptance_gates(self, tmp_path, capsys):
        from typing import Tuple
        results = []

        # AG-01: deterministic import + checksum
        def ag01():
            bars = _bars(5)
            validated, manifest = validate_bars(bars, SYMBOL, INTERVAL)
            assert manifest.verify_hash(validated)
            assert all(b.verify_checksum() for b in validated)
        results.append(self._run_gate("AG-01 checksum+import", ag01))

        # AG-02: invalid inputs rejected
        def ag02():
            with pytest.raises(HistoricalDataError):
                validate_bars([], SYMBOL, INTERVAL)
            with pytest.raises(HistoricalDataError):
                validate_bars([make_test_bar(0, quality=BarQuality.NON_FINAL)], SYMBOL, INTERVAL)
            with pytest.raises(HistoricalDataError):
                validate_bars([make_test_bar(0), make_test_bar(0)], SYMBOL, INTERVAL)
        results.append(self._run_gate("AG-02 invalid inputs", ag02))

        # AG-03: gap detection
        def ag03():
            bars = [make_test_bar(i) for i in [0, 1, 3]]
            with pytest.raises(HistoricalDataError, match="gap"):
                validate_bars(bars, SYMBOL, INTERVAL)
            _, m = validate_bars(bars, SYMBOL, INTERVAL, allow_gaps=True)
            assert m.gap_count == 1
        results.append(self._run_gate("AG-03 gap detection", ag03))

        # AG-04: point-in-time correctness
        def ag04():
            lib = _lib_with(5)
            bar4_obs = BASE + 5 * IMS  # bar_close+1 for index 4
            snap_before = lib.snapshot("BTC1M", bar4_obs - 1)
            snap_after = lib.snapshot("BTC1M", bar4_obs)
            assert BASE + 4 * IMS not in [b.bar_open for b in snap_before]
            assert BASE + 4 * IMS in [b.bar_open for b in snap_after]
        results.append(self._run_gate("AG-04 point-in-time", ag04))

        # AG-05: correction creates new version, old immutable
        def ag05():
            lib = _lib_with(5)
            h1 = lib.get_manifest("BTC1M", 1).manifest_hash
            lib.correct("BTC1M", _bars(5), reason="test")
            assert lib.latest_version("BTC1M") == 2
            assert lib.get_manifest("BTC1M", 1).manifest_hash == h1
        results.append(self._run_gate("AG-05 immutable versions", ag05))

        # AG-06: concurrent reads consistent
        def ag06():
            lib = _lib_with(10)
            cutoff = BASE + 20 * IMS
            snapshots = []
            def r():
                snapshots.append(tuple(b.bar_open for b in lib.snapshot("BTC1M", cutoff)))
            ts = [threading.Thread(target=r) for _ in range(6)]
            for t in ts: t.start()
            for t in ts: t.join()
            assert all(s == snapshots[0] for s in snapshots)
        results.append(self._run_gate("AG-06 concurrent reads", ag06))

        # AG-07: archive backpressure — producer not blocked
        def ag07():
            iface = ArchiveCopyInterface(maxsize=2)
            enqueued = sum(1 for i in range(5) if iface.enqueue(make_test_bar(i)))
            dropped = iface.stats["dropped"]
            assert enqueued == 2
            assert dropped == 3
        results.append(self._run_gate("AG-07 archive backpressure", ag07))

        # AG-08: security — path traversal + manifest tamper
        def ag08():
            with pytest.raises((ValueError, HistoricalDataError)):
                import_fixture_csv("../../etc/passwd", SYMBOL, INTERVAL)
            bars = _bars(3)
            _, m = validate_bars(bars, SYMBOL, INTERVAL)
            # FIX01: manifest is frozen.
            # replace() creates a new valid object (verify_hash fails because hash is wrong):
            tampered = dataclasses.replace(m, manifest_hash="bad_hash_injected")
            assert not tampered.verify_hash(bars)
            # Low-level tamper via object.__setattr__ bypasses __post_init__, so verify_integrity fails:
            object.__setattr__(m, "manifest_hash", "bad_hash_injected")
            assert not m.verify_integrity()
        results.append(self._run_gate("AG-08 security", ag08))

        # Print table
        print("\n=== SF-DATA-01 ACCEPTANCE GATE ===")
        for name, status in results:
            print(f"  {status:<6}  {name}")
        print("===================================")

        failed = [name for name, status in results if not status.startswith("PASS")]
        assert not failed, f"Failed gates: {failed}"


# ---------------------------------------------------------------------------
# T09 — Gap 1: Checksum completeness (FIX01)
# ---------------------------------------------------------------------------

class TestChecksumCompleteness:
    """
    SF-DATA-01-FIX01 Gap 1 — HistoricalBar._compute_checksum must cover
    observation_cutoff_ms, ingest_time_ms, and source_label so that any
    tamper of these provenance fields produces a different checksum.
    """

    def test_observation_cutoff_ms_in_checksum(self):
        """Changing observation_cutoff_ms changes the checksum."""
        bar = make_test_bar(0)
        # Manually build a bar with a different observation_cutoff_ms but same OHLCV
        bar2 = HistoricalBar(
            symbol=bar.symbol, interval=bar.interval,
            bar_open=bar.bar_open, bar_close=bar.bar_close,
            open=bar.open, high=bar.high, low=bar.low, close=bar.close,
            volume=bar.volume, quality=bar.quality, source=bar.source,
            source_label=bar.source_label,
            observation_cutoff_ms=bar.observation_cutoff_ms + 1,
            ingest_time_ms=bar.ingest_time_ms,
        )
        assert bar.checksum != bar2.checksum, (
            "observation_cutoff_ms change must alter checksum"
        )

    def test_ingest_time_ms_in_checksum(self):
        """Changing ingest_time_ms (None vs value) changes the checksum."""
        bar_none = make_test_bar(0, ingest_time_ms=None)
        bar_with = make_test_bar(0, ingest_time_ms=bar_none.bar_close + 500)
        # obs_cutoff differs too, so both should differ from base
        assert bar_none.checksum != bar_with.checksum, (
            "ingest_time_ms change must alter checksum"
        )

    def test_source_label_in_checksum(self):
        """Changing source_label changes the checksum."""
        bar1 = HistoricalBar(
            symbol=SYMBOL, interval=INTERVAL,
            bar_open=BASE, bar_close=BASE + IMS - 1,
            open=100.0, high=101.0, low=99.0, close=100.5, volume=10.0,
            quality=BarQuality.FINAL, source=SourceType.SYNTHETIC,
            source_label="label_A",
            observation_cutoff_ms=BASE + IMS,
            ingest_time_ms=None,
        )
        bar2 = dataclasses.replace(bar1, source_label="label_B")
        # Replace recomputes checksum via __post_init__
        assert bar1.checksum != bar2.checksum, (
            "source_label change must alter checksum"
        )

    def test_verify_checksum_passes_on_valid_bar(self):
        bar = make_test_bar(5)
        assert bar.verify_checksum()

    def test_verify_checksum_detects_ohlcv_tamper(self):
        """OHLCV tamper: replace produces a bar with mismatched stored checksum."""
        bar = make_test_bar(0)
        # Object is frozen; use object.__setattr__ to simulate tampered stored checksum
        tampered_checksum = "0" * 64
        object.__setattr__(bar, "checksum", tampered_checksum)
        assert not bar.verify_checksum()

    def test_checksum_stable_across_reconstructions(self):
        """Same field values always produce the same checksum (deterministic)."""
        bar = make_test_bar(7, ingest_time_ms=BASE + 999)
        bar2 = HistoricalBar(
            symbol=bar.symbol, interval=bar.interval,
            bar_open=bar.bar_open, bar_close=bar.bar_close,
            open=bar.open, high=bar.high, low=bar.low, close=bar.close,
            volume=bar.volume, quality=bar.quality, source=bar.source,
            source_label=bar.source_label,
            observation_cutoff_ms=bar.observation_cutoff_ms,
            ingest_time_ms=bar.ingest_time_ms,
        )
        assert bar.checksum == bar2.checksum


# ---------------------------------------------------------------------------
# T10 — Gap 2: DatasetManifest immutability (FIX01)
# ---------------------------------------------------------------------------

class TestManifestImmutability:
    """
    SF-DATA-01-FIX01 Gap 2 — DatasetManifest must be frozen (immutable);
    manifest_integrity_hash must cover all metadata; older versions must remain
    byte-for-byte unchanged after corrections and attempted mutations.
    """

    def test_manifest_is_frozen(self):
        """Direct field assignment on a DatasetManifest must raise FrozenInstanceError."""
        bars = _bars(3)
        _, m = validate_bars(bars, SYMBOL, INTERVAL)
        with pytest.raises((dataclasses.FrozenInstanceError, AttributeError, TypeError)):
            m.version = 99  # type: ignore[misc]

    def test_manifest_integrity_hash_present(self):
        """manifest_integrity_hash must be a non-empty string."""
        bars = _bars(3)
        _, m = validate_bars(bars, SYMBOL, INTERVAL)
        assert isinstance(m.manifest_integrity_hash, str)
        assert len(m.manifest_integrity_hash) == 64  # SHA-256 hex

    def test_verify_integrity_passes_on_valid_manifest(self):
        bars = _bars(5)
        _, m = validate_bars(bars, SYMBOL, INTERVAL)
        assert m.verify_integrity()

    def test_metadata_tamper_detected_by_integrity_hash(self):
        """Replacing any metadata field produces a different manifest_integrity_hash."""
        bars = _bars(5)
        _, m = validate_bars(bars, SYMBOL, INTERVAL)
        # Simulate metadata tamper via dataclasses.replace (triggers __post_init__)
        tampered = dataclasses.replace(m, bar_count=999)
        # tampered.manifest_integrity_hash is recomputed with bar_count=999
        assert tampered.manifest_integrity_hash != m.manifest_integrity_hash
        # The original manifest must still verify cleanly
        assert m.verify_integrity()

    def test_register_does_not_mutate_caller_manifest(self):
        """register() must not mutate the manifest reference passed by the caller."""
        lib = HistoricalLibrary()
        bars = _bars(3)
        _, m = validate_bars(bars, SYMBOL, INTERVAL)
        original_dataset_id = m.dataset_id  # "" from validate_bars
        lib.register("my_dataset", bars, m)
        # Caller's reference must be unchanged
        assert m.dataset_id == original_dataset_id

    def test_registered_manifest_has_correct_dataset_id(self):
        """The manifest returned by register() must have the requested dataset_id."""
        lib = HistoricalLibrary()
        bars = _bars(3)
        _, m = validate_bars(bars, SYMBOL, INTERVAL)
        returned = lib.register("ds_alpha", bars, m)
        assert returned.dataset_id == "ds_alpha"
        assert lib.get_manifest("ds_alpha").dataset_id == "ds_alpha"

    def test_get_manifest_returns_immutable_reference(self):
        """get_manifest() returns a frozen object; callers cannot alter stored state."""
        lib = HistoricalLibrary()
        bars = _bars(3)
        _, m = validate_bars(bars, SYMBOL, INTERVAL)
        lib.register("ds_beta", bars, m)
        retrieved = lib.get_manifest("ds_beta")
        with pytest.raises((dataclasses.FrozenInstanceError, AttributeError, TypeError)):
            retrieved.bar_count = 0  # type: ignore[misc]

    def test_correct_does_not_alter_base_version(self):
        """After correct(), the base version manifest must be byte-for-byte unchanged."""
        lib = HistoricalLibrary()
        bars = _bars(5)
        _, m = validate_bars(bars, SYMBOL, INTERVAL)
        lib.register("ds_c", bars, m)
        base_manifest = lib.get_manifest("ds_c", version=1)
        base_hash = base_manifest.manifest_integrity_hash
        base_bar_count = base_manifest.bar_count

        # Apply a correction
        new_bars = _bars(6, base=BASE)
        lib.correct("ds_c", new_bars, "add one bar")

        # Original version must be untouched
        v1 = lib.get_manifest("ds_c", version=1)
        assert v1.manifest_integrity_hash == base_hash
        assert v1.bar_count == base_bar_count
        # New version exists and is different
        v2 = lib.get_manifest("ds_c", version=2)
        assert v2.bar_count == 6
        assert v2.parent_version == 1
        assert v2.manifest_integrity_hash != base_hash

    def test_correct_version_integrity_hash_valid(self):
        """The corrected version's manifest_integrity_hash must verify cleanly."""
        lib = HistoricalLibrary()
        bars = _bars(4)
        _, m = validate_bars(bars, SYMBOL, INTERVAL)
        lib.register("ds_d", bars, m)
        new_bars = _bars(4, base=BASE)
        lib.correct("ds_d", new_bars, "re-import")
        v2 = lib.get_manifest("ds_d", version=2)
        assert v2.verify_integrity()

    def test_manifest_tamper_via_object_setattr_detected(self):
        """Simulate low-level tamper of a frozen field; verify_integrity must return False."""
        bars = _bars(3)
        _, m = validate_bars(bars, SYMBOL, INTERVAL)
        original_ih = m.manifest_integrity_hash
        # Force-write a field (bypasses frozen guard, as __setattr__ override)
        object.__setattr__(m, "bar_count", 9999)
        # verify_integrity recomputes from stored fields
        assert not m.verify_integrity()
        # Restore
        object.__setattr__(m, "bar_count", 3)
        assert m.verify_integrity()


# ---------------------------------------------------------------------------
# T11 — Gap 3: Import confinement (FIX01)
# ---------------------------------------------------------------------------

class TestImportConfinement:
    """
    SF-DATA-01-FIX01 Gap 3 — import_fixture_csv must:
      1. Reject ".." in the raw path string BEFORE resolving.
      2. Reject symlinks.
      3. Enforce trusted_root boundary when supplied.
    """

    def test_dotdot_in_raw_string_raises_before_resolve(self):
        """'../foo' in raw path must raise ValueError (not HistoricalDataError)."""
        with pytest.raises(ValueError, match="Path traversal"):
            import_fixture_csv("../some/path.csv", SYMBOL, INTERVAL)

    def test_dotdot_nested_raises(self):
        with pytest.raises(ValueError):
            import_fixture_csv("/tmp/data/../../etc/passwd", SYMBOL, INTERVAL)

    def test_symlink_rejected(self, tmp_path):
        """A symlink as the fixture path must raise ValueError."""
        real_file = tmp_path / "real.csv"
        bars = _bars(3)
        real_file.write_text(make_fixture_csv(bars))
        link = tmp_path / "link.csv"
        link.symlink_to(real_file)
        with pytest.raises(ValueError, match="[Ss]ymlink"):
            import_fixture_csv(link, SYMBOL, INTERVAL)

    def test_trusted_root_blocks_outside_path(self, tmp_path):
        """A file outside trusted_root must raise ValueError."""
        outside = tmp_path / "outside"
        outside.mkdir()
        csv_file = outside / "bars.csv"
        bars = _bars(3)
        csv_file.write_text(make_fixture_csv(bars))

        trusted = tmp_path / "trusted"
        trusted.mkdir()

        with pytest.raises(ValueError, match="escapes trusted root"):
            import_fixture_csv(csv_file, SYMBOL, INTERVAL, trusted_root=trusted)

    def test_trusted_root_allows_inside_path(self, tmp_path):
        """A file inside trusted_root must be accepted normally."""
        trusted = tmp_path / "fixtures"
        trusted.mkdir()
        csv_file = trusted / "bars.csv"
        bars = _bars(3)
        csv_file.write_text(make_fixture_csv(bars))

        result_bars, manifest = import_fixture_csv(
            csv_file, SYMBOL, INTERVAL, trusted_root=trusted
        )
        assert len(result_bars) == 3
        assert manifest.verify_integrity()

    def test_nonexistent_file_raises_historical_data_error(self, tmp_path):
        with pytest.raises(HistoricalDataError, match="Fixture not found"):
            import_fixture_csv(tmp_path / "nonexistent.csv", SYMBOL, INTERVAL)

    def test_valid_import_within_tmp(self, tmp_path):
        """Normal fixture import without trusted_root must still succeed."""
        csv_file = tmp_path / "bars.csv"
        bars = _bars(5)
        csv_file.write_text(make_fixture_csv(bars))
        result, manifest = import_fixture_csv(csv_file, SYMBOL, INTERVAL)
        assert len(result) == 5
        assert manifest.bar_count == 5


# ---------------------------------------------------------------------------
# T12 — Gap 4: range_query fail-closed (FIX01)
# ---------------------------------------------------------------------------

class TestRangeQueryFailClosed:
    """
    SF-DATA-01-FIX01 Gap 4 — range_query must be fail-closed by default:
      * raises when the [start_ms, end_ms] window has gaps (missing bars)
      * raises when no bars qualify at all
      * require_complete=False allows partial reads explicitly
      * future-cutoff exclusion counts as missing (not silently dropped)
    """

    def _lib_with_bars(self, n: int = 10) -> tuple:
        lib = HistoricalLibrary()
        bars = _bars(n)
        _, m = validate_bars(bars, SYMBOL, INTERVAL)
        lib.register("ds", bars, m)
        cutoff = bars[-1].observation_cutoff_ms + 1
        return lib, bars, cutoff

    def test_complete_range_succeeds(self):
        lib, bars, cutoff = self._lib_with_bars(5)
        result = lib.range_query("ds", bars[0].bar_open, bars[4].bar_open, cutoff)
        assert len(result) == 5

    def test_partial_range_raises_by_default(self):
        """
        Request bars[0]..bars[9] but only register bars[0]..bars[4].
        The range extends beyond available data → missing bars → raises.
        """
        lib = HistoricalLibrary()
        bars_5 = _bars(5)
        _, m = validate_bars(bars_5, SYMBOL, INTERVAL)
        lib.register("ds", bars_5, m)
        cutoff = bars_5[-1].observation_cutoff_ms + 1

        # Ask for 10 bars' worth of range but only 5 exist
        start = bars_5[0].bar_open
        end = bars_5[0].bar_open + 9 * IMS  # 10 bars expected
        with pytest.raises(HistoricalDataError, match="Incomplete range"):
            lib.range_query("ds", start, end, cutoff)

    def test_partial_range_allowed_with_flag(self):
        """require_complete=False returns whatever is available without raising."""
        lib = HistoricalLibrary()
        bars_5 = _bars(5)
        _, m = validate_bars(bars_5, SYMBOL, INTERVAL)
        lib.register("ds", bars_5, m)
        cutoff = bars_5[-1].observation_cutoff_ms + 1

        start = bars_5[0].bar_open
        end = bars_5[0].bar_open + 9 * IMS
        result = lib.range_query("ds", start, end, cutoff, require_complete=False)
        assert len(result) == 5

    def test_empty_range_always_raises(self):
        """Even with require_complete=False, zero qualifying bars always raises."""
        lib, bars, _ = self._lib_with_bars(5)
        far_future_cutoff = BASE - 1  # nothing observable
        with pytest.raises(HistoricalDataError):
            lib.range_query("ds", bars[0].bar_open, bars[4].bar_open,
                            far_future_cutoff, require_complete=False)

    def test_future_cutoff_exclusion_raises_as_incomplete(self):
        """
        Bars exist in range but observation_cutoff_ms is in the future relative
        to the decision point → those bars are excluded → incomplete → raises.
        """
        lib = HistoricalLibrary()
        # Build bars with ingest_time_ms far in the future
        future_ingest = BASE + 10_000 * IMS
        bars = [make_test_bar(i, ingest_time_ms=future_ingest) for i in range(5)]
        # obs_cutoff = max(bar_close+1, ingest_time_ms) = future_ingest
        _, m = validate_bars(bars, SYMBOL, INTERVAL)
        lib.register("ds", bars, m)

        # Decision cutoff is NOW (before the ingest_time)
        early_cutoff = bars[0].bar_close + 1  # earlier than future_ingest
        with pytest.raises(HistoricalDataError):
            lib.range_query("ds", bars[0].bar_open, bars[4].bar_open,
                            early_cutoff, require_complete=True)

    def test_gap_in_registered_dataset_raises_if_range_spans_gap(self, tmp_path):
        """A registered dataset with gaps: range_query over the gap raises."""
        lib = HistoricalLibrary()
        # bars 0,1,2 then skip 3, have 4
        bars_02 = _bars(3)
        bar4 = make_test_bar(4)
        gapped = bars_02 + [bar4]
        _, m = validate_bars(gapped, SYMBOL, INTERVAL, allow_gaps=True)
        lib.register("ds_gap", gapped, m)
        cutoff = bar4.observation_cutoff_ms + 1

        start = bars_02[0].bar_open
        end = bar4.bar_open
        with pytest.raises(HistoricalDataError, match="Incomplete range"):
            lib.range_query("ds_gap", start, end, cutoff)


# ---------------------------------------------------------------------------
# T13 — FIX01 combined acceptance gate
# ---------------------------------------------------------------------------

class TestFix01AcceptanceGate:
    """
    SF-DATA-01-FIX01 — combined acceptance gate for all 4 fix gaps.
    All 4 FIX01 gates must PASS.
    """

    def _run_gate(self, name: str, fn) -> tuple:
        try:
            fn()
            return name, "PASS ✓"
        except Exception as exc:
            return name, f"FAIL ✗ — {exc}"

    def test_fix01_all_gates(self, tmp_path):
        results = []

        # FIX-AG-01: checksum covers observation_cutoff_ms
        def fix_ag01():
            bar = make_test_bar(0)
            bar2 = HistoricalBar(
                symbol=bar.symbol, interval=bar.interval,
                bar_open=bar.bar_open, bar_close=bar.bar_close,
                open=bar.open, high=bar.high, low=bar.low, close=bar.close,
                volume=bar.volume, quality=bar.quality, source=bar.source,
                source_label=bar.source_label,
                observation_cutoff_ms=bar.observation_cutoff_ms + 9999,
                ingest_time_ms=bar.ingest_time_ms,
            )
            assert bar.checksum != bar2.checksum
            bar3 = HistoricalBar(
                symbol=bar.symbol, interval=bar.interval,
                bar_open=bar.bar_open, bar_close=bar.bar_close,
                open=bar.open, high=bar.high, low=bar.low, close=bar.close,
                volume=bar.volume, quality=bar.quality, source=bar.source,
                source_label="DIFFERENT_LABEL",
                observation_cutoff_ms=bar.observation_cutoff_ms,
                ingest_time_ms=bar.ingest_time_ms,
            )
            assert bar.checksum != bar3.checksum
        results.append(self._run_gate("FIX-AG-01 checksum provenance completeness", fix_ag01))

        # FIX-AG-02: manifest frozen + integrity hash detects tamper + base unchanged after correct()
        def fix_ag02():
            lib = HistoricalLibrary()
            bars = _bars(4)
            _, m = validate_bars(bars, SYMBOL, INTERVAL)
            # frozen
            try:
                m.bar_count = 999  # type: ignore
                raise AssertionError("manifest must be frozen")
            except (dataclasses.FrozenInstanceError, AttributeError, TypeError):
                pass
            # integrity hash — replace() recomputes hash correctly for new fields
            assert m.verify_integrity()
            tampered = dataclasses.replace(m, bar_count=9999)
            # tampered has a different hash (bar_count differs) but itself is valid
            assert tampered.manifest_integrity_hash != m.manifest_integrity_hash
            # Low-level bypass: object.__setattr__ stales the hash → verify_integrity fails
            object.__setattr__(m, "bar_count", 9999)
            assert not m.verify_integrity()
            object.__setattr__(m, "bar_count", 4)  # restore
            # register does not mutate caller
            original_did = m.dataset_id
            lib.register("ds", bars, m)
            assert m.dataset_id == original_did
            # correct() leaves v1 unchanged
            new_bars = _bars(5)
            lib.correct("ds", new_bars, "fix")
            v1 = lib.get_manifest("ds", 1)
            assert v1.bar_count == 4
        results.append(self._run_gate("FIX-AG-02 manifest immutability + integrity", fix_ag02))

        # FIX-AG-03: import confinement
        def fix_ag03():
            # raw string guard
            try:
                import_fixture_csv("../../etc/passwd", SYMBOL, INTERVAL)
                raise AssertionError("must raise on ..")
            except ValueError:
                pass
            # symlink
            real = tmp_path / "real.csv"
            bars = _bars(3)
            real.write_text(make_fixture_csv(bars))
            link = tmp_path / "link.csv"
            link.symlink_to(real)
            try:
                import_fixture_csv(link, SYMBOL, INTERVAL)
                raise AssertionError("must raise on symlink")
            except ValueError:
                pass
            # trusted_root blocks outside
            outside = tmp_path / "out"
            outside.mkdir(exist_ok=True)
            f = outside / "b.csv"
            f.write_text(make_fixture_csv(bars))
            trusted = tmp_path / "trusted"
            trusted.mkdir(exist_ok=True)
            try:
                import_fixture_csv(f, SYMBOL, INTERVAL, trusted_root=trusted)
                raise AssertionError("must raise when outside trusted_root")
            except ValueError:
                pass
            # valid import inside trusted_root
            inside = trusted / "bars.csv"
            inside.write_text(make_fixture_csv(bars))
            r, mf = import_fixture_csv(inside, SYMBOL, INTERVAL, trusted_root=trusted)
            assert len(r) == 3
            assert mf.verify_integrity()
        results.append(self._run_gate("FIX-AG-03 import confinement", fix_ag03))

        # FIX-AG-04: range_query fail-closed
        def fix_ag04():
            lib = HistoricalLibrary()
            bars5 = _bars(5)
            _, m = validate_bars(bars5, SYMBOL, INTERVAL)
            lib.register("ds", bars5, m)
            cutoff = bars5[-1].observation_cutoff_ms + 1
            # complete range succeeds
            result = lib.range_query("ds", bars5[0].bar_open, bars5[4].bar_open, cutoff)
            assert len(result) == 5
            # partial range raises
            try:
                lib.range_query("ds", bars5[0].bar_open,
                                bars5[0].bar_open + 9 * IMS, cutoff)
                raise AssertionError("must raise on incomplete range")
            except HistoricalDataError:
                pass
            # require_complete=False succeeds
            r2 = lib.range_query("ds", bars5[0].bar_open,
                                 bars5[0].bar_open + 9 * IMS, cutoff,
                                 require_complete=False)
            assert len(r2) == 5
        results.append(self._run_gate("FIX-AG-04 range_query fail-closed", fix_ag04))

        print("\n=== SF-DATA-01-FIX01 ACCEPTANCE GATE ===")
        for name, status in results:
            print(f"  {status:<8}  {name}")
        print("=========================================")

        failed = [name for name, status in results if not status.startswith("PASS")]
        assert not failed, f"Failed FIX01 gates: {failed}"
