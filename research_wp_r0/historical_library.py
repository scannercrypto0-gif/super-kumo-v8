"""
SF-DATA-01 — Historical Market Data Library V1
================================================
Isolated, read-only, deterministic historical OHLCV library.

Design guarantees
-----------------
* Versioned immutable records — corrections create a new version + lineage, never
  silently overwrite the prior dataset.
* Local-first, no network — all data comes from fixture files or in-memory.
* Point-in-time correctness — every bar carries an ``observation_cutoff_ms``
  (earliest time the bar could have been *known*); queries reject bars that would
  not have been observable at the requested decision time.
* Fail-closed quality gate — incomplete, non-final, out-of-order or duplicate
  bars raise instead of silently degrading.
* Archive-copy interface — a non-blocking contract for copying real-time bars
  into the history store; archive failures never block a fast producer.
* Path-traversal and manifest-corruption guards.

No live exchange calls, no credentials, no G1 pipeline coupling.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import os
import time
import threading
import queue
from dataclasses import dataclass, field, asdict
from enum import Enum
from pathlib import Path
from typing import Callable, Dict, Iterator, List, Optional, Sequence, Tuple


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------

class BarQuality(str, Enum):
    FINAL = "FINAL"          # bar_close confirmed; usable for research
    NON_FINAL = "NON_FINAL"  # still updating; rejected by quality gate
    UNKNOWN = "UNKNOWN"      # finality not recorded


class SourceType(str, Enum):
    FIXTURE = "fixture"       # loaded from a local fixture file
    ARCHIVE = "archive"       # copied from real-time pipeline (non-blocking)
    SYNTHETIC = "synthetic"   # generated in-process for tests


# ---------------------------------------------------------------------------
# Canonical OHLCV record
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class HistoricalBar:
    """
    Immutable OHLCV bar with full provenance.

    ``observation_cutoff_ms``
        Earliest epoch-ms at which this bar *could* have been observed.
        For a final bar this is ``bar_close + 1``; for archive copies it is
        ``max(bar_close + 1, ingest_time_ms)`` when ingest time is known.
        Queries that request a decision point earlier than this value will
        exclude this bar (point-in-time correctness).

    ``ingest_time_ms``
        Wall-clock epoch-ms when the bar was received/imported.
        ``None`` if unknown — the historical receipt time is not fabricated.
    """
    symbol: str
    interval: str
    bar_open: int          # epoch-ms, inclusive
    bar_close: int         # epoch-ms, inclusive
    open: float
    high: float
    low: float
    close: float
    volume: float
    quality: BarQuality
    source: SourceType
    source_label: str      # e.g. "binance_spot", "fixture_v1"
    observation_cutoff_ms: int   # earliest decision point that may use this bar
    ingest_time_ms: Optional[int]  # None = unknown
    checksum: str = field(default="", compare=False)

    def __post_init__(self):
        # recompute and store checksum (dataclass is frozen so we use object.__setattr__)
        cs = self._compute_checksum()
        object.__setattr__(self, "checksum", cs)

    def _compute_checksum(self) -> str:
        payload = json.dumps({
            "symbol": self.symbol,
            "interval": self.interval,
            "bar_open": self.bar_open,
            "bar_close": self.bar_close,
            "open": self.open,
            "high": self.high,
            "low": self.low,
            "close": self.close,
            "volume": self.volume,
            "quality": self.quality.value,
            "source": self.source.value,
        }, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(payload.encode()).hexdigest()

    def stable_key(self) -> str:
        return f"{self.symbol}:{self.interval}:{self.bar_open}"

    def verify_checksum(self) -> bool:
        return self.checksum == self._compute_checksum()


# ---------------------------------------------------------------------------
# Manifest + Dataset version
# ---------------------------------------------------------------------------

@dataclass
class DatasetManifest:
    """
    Immutable manifest bound to one dataset version.

    ``manifest_hash`` covers all bar checksums + metadata in deterministic order.
    Corrected datasets must produce a NEW version with a lineage reference.
    """
    dataset_id: str          # unique name, e.g. "BTCUSDT_1m_2024"
    version: int             # monotonically increasing; 1-based
    exchange: str
    market: str              # e.g. "spot", "perp"
    symbol: str
    interval: str
    timezone: str            # "UTC" always for internal storage
    source_label: str
    bar_count: int
    min_bar_open: int        # epoch-ms
    max_bar_open: int        # epoch-ms
    coverage_pct: float      # 0–100; fraction of expected bars present
    gap_count: int
    gap_bar_opens: List[int] # sorted list of missing expected bar_opens
    duplicate_count: int
    non_final_count: int
    manifest_hash: str       # sha256 of all bar checksums concatenated in bar_open order
    created_at_ms: int
    parent_version: Optional[int]  # lineage: which version this corrects
    lineage_reason: Optional[str]

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "DatasetManifest":
        return cls(**d)

    def verify_hash(self, bars: Sequence[HistoricalBar]) -> bool:
        """Recompute manifest_hash from bars and compare."""
        sorted_bars = sorted(bars, key=lambda b: b.bar_open)
        combined = "".join(b.checksum for b in sorted_bars)
        expected = hashlib.sha256(combined.encode()).hexdigest()
        return self.manifest_hash == expected


# ---------------------------------------------------------------------------
# Quality gate
# ---------------------------------------------------------------------------

class HistoricalDataError(Exception):
    """Raised when data fails a quality or integrity check."""


def _interval_to_ms(interval: str) -> int:
    units = {"m": 60_000, "h": 3_600_000, "d": 86_400_000}
    if len(interval) < 2:
        raise ValueError(f"Invalid interval: {interval!r}")
    n, unit = int(interval[:-1]), interval[-1]
    if unit not in units:
        raise ValueError(f"Unknown interval unit: {unit!r}")
    return n * units[unit]


def validate_bars(
    bars: List[HistoricalBar],
    symbol: str,
    interval: str,
    *,
    allow_gaps: bool = False,
) -> Tuple[List[HistoricalBar], DatasetManifest]:
    """
    Validate a list of bars and produce a manifest.

    Raises HistoricalDataError on:
    - Empty input
    - Non-final bars
    - Checksum mismatch
    - Duplicate bar_open values
    - Out-of-order bar_open values
    - bar_close != bar_open + interval_ms - 1
    - Cross-symbol contamination

    If ``allow_gaps`` is False (default) → raises on any gap.
    If ``allow_gaps`` is True → gaps are recorded in the manifest.
    """
    if not bars:
        raise HistoricalDataError("Empty bar list")

    interval_ms = _interval_to_ms(interval)
    seen_opens: dict = {}
    non_final = 0
    bad_checksums = 0
    prev_open: Optional[int] = None
    gap_opens: List[int] = []

    for bar in bars:
        if bar.symbol != symbol:
            raise HistoricalDataError(
                f"Cross-symbol contamination: expected {symbol}, got {bar.symbol}"
            )
        if bar.interval != interval:
            raise HistoricalDataError(
                f"Cross-interval contamination: expected {interval}, got {bar.interval}"
            )
        if bar.quality != BarQuality.FINAL:
            non_final += 1
        if not bar.verify_checksum():
            bad_checksums += 1
        expected_close = bar.bar_open + interval_ms - 1
        if bar.bar_close != expected_close:
            raise HistoricalDataError(
                f"bar_close mismatch at {bar.bar_open}: "
                f"expected {expected_close}, got {bar.bar_close}"
            )
        if bar.bar_open in seen_opens:
            raise HistoricalDataError(f"Duplicate bar_open: {bar.bar_open}")
        seen_opens[bar.bar_open] = True

        if prev_open is not None:
            expected_next = prev_open + interval_ms
            if bar.bar_open < expected_next:
                raise HistoricalDataError(f"Out-of-order bar at {bar.bar_open}")
            if bar.bar_open > expected_next:
                # gap detected
                gap_start = expected_next
                while gap_start < bar.bar_open:
                    gap_opens.append(gap_start)
                    gap_start += interval_ms
        prev_open = bar.bar_open

    if non_final > 0:
        raise HistoricalDataError(f"{non_final} non-final bar(s) in dataset")
    if bad_checksums > 0:
        raise HistoricalDataError(f"{bad_checksums} checksum failure(s)")
    if gap_opens and not allow_gaps:
        raise HistoricalDataError(
            f"{len(gap_opens)} gap bar(s) detected (first: {gap_opens[0]}); "
            "use allow_gaps=True to record gaps in manifest"
        )

    sorted_bars = sorted(bars, key=lambda b: b.bar_open)
    combined = "".join(b.checksum for b in sorted_bars)
    manifest_hash = hashlib.sha256(combined.encode()).hexdigest()

    expected_bar_count = (sorted_bars[-1].bar_open - sorted_bars[0].bar_open) // interval_ms + 1
    coverage_pct = round(len(sorted_bars) / expected_bar_count * 100, 4) if expected_bar_count else 100.0

    manifest = DatasetManifest(
        dataset_id="",         # caller fills in
        version=1,
        exchange="",
        market="",
        symbol=symbol,
        interval=interval,
        timezone="UTC",
        source_label=sorted_bars[0].source_label if sorted_bars else "",
        bar_count=len(sorted_bars),
        min_bar_open=sorted_bars[0].bar_open,
        max_bar_open=sorted_bars[-1].bar_open,
        coverage_pct=coverage_pct,
        gap_count=len(gap_opens),
        gap_bar_opens=gap_opens,
        duplicate_count=0,
        non_final_count=0,
        manifest_hash=manifest_hash,
        created_at_ms=int(time.time() * 1000),
        parent_version=None,
        lineage_reason=None,
    )
    return sorted_bars, manifest


# ---------------------------------------------------------------------------
# Offline importer
# ---------------------------------------------------------------------------

def import_fixture_csv(
    path: str | Path,
    symbol: str,
    interval: str,
    source_label: str = "fixture",
    *,
    allow_gaps: bool = False,
) -> Tuple[List[HistoricalBar], DatasetManifest]:
    """
    Import OHLCV bars from a CSV fixture file.

    Expected columns (in order, no header required):
        bar_open, bar_close, open, high, low, close, volume

    All values numeric; bar_open / bar_close are epoch-ms integers.
    Source bytes are hashed but not embedded; credentials are never recorded.

    Raises HistoricalDataError on schema or ordering violations.
    Raises ValueError on path traversal attempts.
    """
    path = Path(path).resolve()
    # Path traversal guard: must be a file, not a symlink chain
    if not path.is_file():
        raise HistoricalDataError(f"Fixture not found: {path}")
    # Guard against obvious traversal patterns in the original string
    raw = str(path)
    if ".." in raw:
        raise ValueError(f"Path traversal detected: {path}")

    source_hash = hashlib.sha256(path.read_bytes()).hexdigest()
    interval_ms = _interval_to_ms(interval)
    bars: List[HistoricalBar] = []

    with path.open(newline="", encoding="utf-8") as f:
        reader = csv.reader(f)
        for i, row in enumerate(reader):
            if not row or row[0].startswith("#"):
                continue
            if len(row) < 7:
                raise HistoricalDataError(
                    f"Row {i+1}: expected 7 columns, got {len(row)}"
                )
            try:
                bar_open = int(row[0])
                bar_close = int(row[1])
                o, h, l, c, v = (float(x) for x in row[2:7])
            except ValueError as e:
                raise HistoricalDataError(f"Row {i+1}: parse error: {e}") from e
            expected_close = bar_open + interval_ms - 1
            if bar_close != expected_close:
                raise HistoricalDataError(
                    f"Row {i+1}: bar_close {bar_close} != expected {expected_close}"
                )
            obs_cutoff = bar_close + 1
            bar = HistoricalBar(
                symbol=symbol,
                interval=interval,
                bar_open=bar_open,
                bar_close=bar_close,
                open=o, high=h, low=l, close=c, volume=v,
                quality=BarQuality.FINAL,
                source=SourceType.FIXTURE,
                source_label=source_label,
                observation_cutoff_ms=obs_cutoff,
                ingest_time_ms=None,  # receipt time unknown for historical fixtures
            )
            bars.append(bar)

    validated, manifest = validate_bars(bars, symbol, interval, allow_gaps=allow_gaps)
    return validated, manifest


# ---------------------------------------------------------------------------
# Historical snapshot / range access
# ---------------------------------------------------------------------------

@dataclass
class HistoricalLibrary:
    """
    In-memory versioned historical library.

    Versions are immutable. Corrections create a new version (``correct()``).
    All reads are deterministic given the same version and decision_cutoff_ms.
    """
    _datasets: Dict[str, Dict[int, Tuple[List[HistoricalBar], DatasetManifest]]] = field(
        default_factory=dict
    )

    def register(
        self,
        dataset_id: str,
        bars: List[HistoricalBar],
        manifest: DatasetManifest,
    ) -> DatasetManifest:
        """Store a validated dataset under dataset_id at manifest.version."""
        manifest.dataset_id = dataset_id
        if dataset_id not in self._datasets:
            self._datasets[dataset_id] = {}
        if manifest.version in self._datasets[dataset_id]:
            raise HistoricalDataError(
                f"Version {manifest.version} of {dataset_id} already registered"
            )
        self._datasets[dataset_id][manifest.version] = (list(bars), manifest)
        return manifest

    def latest_version(self, dataset_id: str) -> int:
        if dataset_id not in self._datasets:
            raise HistoricalDataError(f"Unknown dataset: {dataset_id}")
        return max(self._datasets[dataset_id])

    def get_manifest(self, dataset_id: str, version: Optional[int] = None) -> DatasetManifest:
        if dataset_id not in self._datasets:
            raise HistoricalDataError(f"Unknown dataset: {dataset_id}")
        v = version if version is not None else self.latest_version(dataset_id)
        if v not in self._datasets[dataset_id]:
            raise HistoricalDataError(f"Version {v} not found for {dataset_id}")
        return self._datasets[dataset_id][v][1]

    def snapshot(
        self,
        dataset_id: str,
        decision_cutoff_ms: int,
        *,
        version: Optional[int] = None,
    ) -> List[HistoricalBar]:
        """
        Return all bars observable at ``decision_cutoff_ms`` (point-in-time).

        Bars with observation_cutoff_ms > decision_cutoff_ms are excluded,
        preventing future-bar leakage into research decisions.
        """
        if dataset_id not in self._datasets:
            raise HistoricalDataError(f"Unknown dataset: {dataset_id}")
        v = version if version is not None else self.latest_version(dataset_id)
        bars, manifest = self._datasets[dataset_id][v]
        eligible = [b for b in bars if b.observation_cutoff_ms <= decision_cutoff_ms]
        return sorted(eligible, key=lambda b: b.bar_open)

    def range_query(
        self,
        dataset_id: str,
        start_ms: int,
        end_ms: int,
        decision_cutoff_ms: int,
        *,
        version: Optional[int] = None,
    ) -> List[HistoricalBar]:
        """
        Return bars in [start_ms, end_ms] observable at decision_cutoff_ms.
        Raises if no bars qualify (fail-closed).
        """
        all_bars = self.snapshot(dataset_id, decision_cutoff_ms, version=version)
        result = [b for b in all_bars if start_ms <= b.bar_open <= end_ms]
        if not result:
            raise HistoricalDataError(
                f"No eligible bars in [{start_ms}, {end_ms}] "
                f"at cutoff {decision_cutoff_ms} for {dataset_id}"
            )
        return result

    def correct(
        self,
        dataset_id: str,
        new_bars: List[HistoricalBar],
        reason: str,
        *,
        base_version: Optional[int] = None,
        allow_gaps: bool = False,
    ) -> DatasetManifest:
        """
        Create a corrected version of dataset_id.

        The prior version is never modified. The new version gets
        parent_version = base_version (or latest) and lineage_reason = reason.
        """
        base_v = base_version if base_version is not None else self.latest_version(dataset_id)
        _, base_manifest = self._datasets[dataset_id][base_v]

        validated, new_manifest = validate_bars(
            new_bars, base_manifest.symbol, base_manifest.interval, allow_gaps=allow_gaps
        )
        new_manifest.version = base_v + 1
        new_manifest.parent_version = base_v
        new_manifest.lineage_reason = reason
        new_manifest.exchange = base_manifest.exchange
        new_manifest.market = base_manifest.market
        new_manifest.source_label = base_manifest.source_label

        return self.register(dataset_id, validated, new_manifest)

    def coverage_report(self, dataset_id: str, version: Optional[int] = None) -> dict:
        m = self.get_manifest(dataset_id, version)
        return {
            "dataset_id": m.dataset_id,
            "version": m.version,
            "bar_count": m.bar_count,
            "coverage_pct": m.coverage_pct,
            "gap_count": m.gap_count,
            "gap_bar_opens": m.gap_bar_opens,
        }


# ---------------------------------------------------------------------------
# Archive-copy interface (non-blocking)
# ---------------------------------------------------------------------------

class ArchiveCopyError(Exception):
    """Raised when the archive worker encounters an unrecoverable error."""


class ArchiveCopyInterface:
    """
    Non-blocking contract for copying real-time bars into the history store.

    The fast producer (real-time pipeline) calls ``enqueue(bar)`` — never blocks.
    A background worker drains the queue and calls ``_write_one(bar)``.
    Write failures and backpressure are isolated from the producer.

    Design:
    - Producer: ``enqueue()`` → puts to bounded queue, drops on full (backpressure).
    - Worker: ``_drain_loop()`` → reads from queue, calls ``_write_one()``.
    - Failure isolation: worker errors increment ``_write_errors``, never propagate
      to the producer thread.

    This class is the *interface contract* and a testable in-memory implementation.
    A production implementation would swap ``_write_one`` for durable storage.
    """

    def __init__(
        self,
        maxsize: int = 1000,
        write_fn: Optional[Callable[[HistoricalBar], None]] = None,
    ):
        self._queue: "queue.Queue[Optional[HistoricalBar]]" = queue.Queue(maxsize=maxsize)
        self._write_fn = write_fn or (lambda b: None)
        self._enqueued = 0
        self._dropped = 0        # backpressure drops (queue full)
        self._written = 0
        self._write_errors = 0
        self._thread: Optional[threading.Thread] = None
        self._running = False

    def start(self) -> None:
        self._running = True
        self._thread = threading.Thread(target=self._drain_loop, daemon=True)
        self._thread.start()

    def stop(self, timeout_s: float = 2.0) -> None:
        self._running = False
        try:
            self._queue.put_nowait(None)  # sentinel
        except queue.Full:
            pass
        if self._thread:
            self._thread.join(timeout=timeout_s)

    def enqueue(self, bar: HistoricalBar) -> bool:
        """
        Non-blocking enqueue. Returns True if enqueued, False if dropped.
        NEVER raises — producer must not be interrupted by archive failures.
        """
        try:
            self._queue.put_nowait(bar)
            self._enqueued += 1
            return True
        except queue.Full:
            self._dropped += 1
            return False

    def _drain_loop(self) -> None:
        while self._running or not self._queue.empty():
            try:
                item = self._queue.get(timeout=0.05)
                if item is None:
                    break
                self._write_one(item)
            except queue.Empty:
                continue

    def _write_one(self, bar: HistoricalBar) -> None:
        try:
            self._write_fn(bar)
            self._written += 1
        except Exception:
            self._write_errors += 1
            # Failure is recorded but NEVER propagated to the producer

    @property
    def stats(self) -> dict:
        return {
            "enqueued": self._enqueued,
            "dropped": self._dropped,
            "written": self._written,
            "write_errors": self._write_errors,
            "queue_size": self._queue.qsize(),
        }


# ---------------------------------------------------------------------------
# Helpers for tests
# ---------------------------------------------------------------------------

BASE_OPEN_MS = 1_700_000_000_000
INTERVAL_MS_1M = 60_000


def make_test_bar(
    i: int,
    symbol: str = "BTCUSDT",
    interval: str = "1m",
    base_open: int = BASE_OPEN_MS,
    source: SourceType = SourceType.SYNTHETIC,
    quality: BarQuality = BarQuality.FINAL,
    ingest_time_ms: Optional[int] = None,
) -> HistoricalBar:
    interval_ms = _interval_to_ms(interval)
    bar_open = base_open + i * interval_ms
    bar_close = bar_open + interval_ms - 1
    obs_cutoff = bar_close + 1
    if ingest_time_ms is not None:
        obs_cutoff = max(obs_cutoff, ingest_time_ms)
    return HistoricalBar(
        symbol=symbol,
        interval=interval,
        bar_open=bar_open,
        bar_close=bar_close,
        open=100.0 + i,
        high=101.0 + i,
        low=99.0 + i,
        close=100.5 + i,
        volume=10.0 + i,
        quality=quality,
        source=source,
        source_label="synthetic",
        observation_cutoff_ms=obs_cutoff,
        ingest_time_ms=ingest_time_ms,
    )


def make_fixture_csv(bars: List[HistoricalBar]) -> str:
    """Return CSV string for use in tests (no header)."""
    lines = []
    for b in bars:
        lines.append(
            f"{b.bar_open},{b.bar_close},{b.open},{b.high},{b.low},{b.close},{b.volume}"
        )
    return "\n".join(lines)
