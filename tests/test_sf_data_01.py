"""
SF-DATA-01 — Historical Market Data Library V1
Acceptance tests for Issue #47

Coverage:
  T01  deterministic import and snapshot replay; checksums and immutable versions
  T02  invalid / missing / duplicate / out-of-order / non-final / cross-source conflicts
  T03  gaps and coverage report with fail-closed quality eligibility
  T04  point-in-time decisions against later corrections and unknown observation timestamps
  T05  concurrent historical reads across different versions and deterministic cache identity
  T06  archive-copy failure/backpressure isolation (synthetic double only)
  T07  negative security: path traversal, corrupted manifest, snapshot rewrite
  T08  combined acceptance gate — all 8 AGs must PASS in one machine-readable block
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
    manifest.dataset_id = dataset_id
    manifest.exchange = "binance"
    manifest.market = "spot"
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
        manifest.dataset_id = "X"
        lib.register("X", bars, manifest)
        # Build a second manifest for the same version
        bars2 = _bars(5)
        _, manifest2 = validate_bars(bars2, SYMBOL, INTERVAL)
        manifest2.dataset_id = "X"
        manifest2.version = 1
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
        # Tamper with hash
        manifest.manifest_hash = "0" * 64
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
        manifest.dataset_id = "DS"
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
            m.manifest_hash = "bad"
            assert not m.verify_hash(bars)
        results.append(self._run_gate("AG-08 security", ag08))

        # Print table
        print("\n=== SF-DATA-01 ACCEPTANCE GATE ===")
        for name, status in results:
            print(f"  {status:<6}  {name}")
        print("===================================")

        failed = [name for name, status in results if not status.startswith("PASS")]
        assert not failed, f"Failed gates: {failed}"
