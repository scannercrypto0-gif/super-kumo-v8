Warning: truncated output (original token count: 12733)
Total output lines: 1193

"""
SF-DATA-01 ? Historical Market Data Library V1
================================================
Isolated, read-only, deterministic historical OHLCV library.

Design guarantees
-----------------
* Versioned immutable records ? corrections create a new version + lineage, never
  silently overwrite the prior dataset.
* Local-first, no network ? all data comes from fixture files or in-memory.
* Point-in-time correctness ? every bar carries an ``observation_cutoff_ms``
  (earliest time the bar could have been *known*); queries reject bars that would
  not have been observable at the requested decision time.
* Fail-closed quality gate ? incomplete, non-final, out-of-order or duplicate
  bars raise instead of silently degrading.
* Archive-copy interface ? a non-blocking contract for copying real-time bars
  into the history store; archive failures never block a fast producer.
* Full integrity chain ? bar checksums cover all provenance fields including
  observation_cutoff_ms and source_label; manifest integrity hash covers all
  manifest metadata + the bar-level manifest_hash.
* Import confinement ? symlink rejection, raw-string traversal guard, and
  optional trusted_root boundary enforcement.
* Fail-closed range queries ? range_query verifies complete contiguous coverage
  by default; partial reads are opt-in via require_complete=False.

No live exchange calls, no credentials, no G1 pipeline coupling.

SF-DATA-01-FIX01 (Issue #50) changes vs original SF-DATA-01:
  - HistoricalBar._compute_checksum: adds observation_cutoff_ms, ingest_time_ms,
    source_label to SHA-256 payload (Gap 1)
  - DatasetManifest: frozen=True + manifest_integrity_hash field covering all
    metadata + manifest_hash; verify_integrity() method (Gap 2)
  - register() / correct(): use dataclasses.replace() ? no direct field mutation
    on frozen instances (Gap 2)
  - import_fixture_csv: raw-string guard BEFORE resolve(), symlink rejection,
    optional trusted_root parameter (Gap 3)
  - range_query: require_complete=True default; raises on partial coverage (Gap 4)

SF-DATA-01-FIX02 (Issue #50 owner review 2026-10-23) changes vs FIX01:
  - Blocker 1: CI workflow updated to include test_sf_data_01.py in discovery
  - Blocker 2: DatasetManifest.gap_bar_opens: List?Tuple[int,...]; integrity hash
    now covers gap_bar_opens, duplicate_count, non_final_count, created_at_ms
  - Blocker 3: register() validates bar checksums, manifest_hash, integrity_hash;
    from_dict() validates stored hash against recomputed (no silent laundering)
  - Blocker 4: validate_bars() checks math.isfinite, positive prices, nonneg
    volume, and OHLC ordering (high?max(O,C,L); low?min(O,C,H))
  - Blocker 5: DataAvailabilityKind enum; availability_kind field on HistoricalBar
    (in checksum); RETROSPECTIVE for fixtures; require_confirmed_availability
    on snapshot() and range_query()
  - Blocker 6: import_fixture_csv reads bytes once (hash+parse from same bytes);
    source_hash bound to manifest via dataclasses.replace()
"""
from __future__ import annotations

import csv
import dataclasses
import hashlib
import io
import json
import math
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


class DataAvailabilityKind(str, Enum):
    """
    Captures whether the observation timestamp is theoretically derived or
    actually recorded.

    FIX02 ? Blocker 5
    -----------------
    RETROSPECTIVE
        Bar was imported from a historical fixture; the actual receipt time is
        unknown.  ``observation_cutoff_ms = bar_close + 1`` is a theoretical
        lower bound ? the bar *could not* have been known before bar close, but
        we have no evidence of when it was actually ingested.  Researchers must
        be aware that any analysis that depends on intra-bar or near-close
        arrival times cannot be reproduced exactly.

    CONFIRMED
        The bar was received in real time; ``ingest_time_ms`` is recorded and
        ``observation_cutoff_ms = max(bar_close + 1, ingest_time_ms)`` reflects
        the actual ingestion wall-clock.  Point-in-time queries can rely on
        this timestamp.
    """
    RETROSPECTIVE = "RETROSPECTIVE"   # obs time unknown; bar_close+1 is theoretical
    CONFIRMED = "CONFIRMED"           # actual ingest time recorded


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
        ``None`` if unknown ? the historical receipt time is not fabricated.

    ``availability_kind``
        Whether the observation timestamp is theoretically derived
        (RETROSPECTIVE, from a fixture) or actually recorded (CONFIRMED, from
        the real-time pipeline).  Included in the checksum so that a fixture
        bar cannot be silently promoted to CONFIRMED without detection.

    ``checksum``
        SHA-256 of a canonical JSON payload covering all OHLCV fields,
        provenance metadata (symbol, interval, quality, source, source_label),
        temporal integrity fields (observation_cutoff_ms, ingest_time_ms),
        AND availability_kind.  Any tamper of ANY field changes the checksum.
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
    # FIX02 ? Blocker 5: distinguishes theoretical (fixture) from recorded timestamps
    availability_kind: DataAvailabilityKind = DataAvailabilityKind.CONFIRMED
    checksum: str = field(default="", compare=False)

    def __post_init__(self):
        if (type(self.observation_cutoff_ms) is not int
                or type(self.bar_close) is not int
                or self.observation_cutoff_ms < self.bar_close + 1):
            raise ValueError("Observation cutoff precedes final-bar availability")
        if (self.ingest_time_ms is not None
                and (type(self.ingest_time_ms) is not int
                     or self.observation_cutoff_ms < self.ingest_time_ms)):
            raise ValueError("Observation cutoff precedes recorded ingestion")
        # recompute and store checksum (dataclass is frozen so we use object.__setattr__)
        cs = self._compute_checksum()
        object.__setattr__(self, "checksum", cs)

    def _compute_checksum(self) -> str:
        """
        SHA-256 over canonical JSON covering all OHLCV + provenance + temporal
        + availability fields.

        FIX01 ? Gap 1: observation_cutoff_ms, ingest_time_ms and source_label
        are included so that any tamper of these fields is detectable.

        FIX02 ? Blocker 5: availability_kind is included so that a RETROSPECTIVE
        fixture bar cannot be silently promoted to CONFIRMED without detection.
        """
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
            # FIX01 additions ? provenance completeness
            "source_label": self.source_label,
            "observation_cutoff_ms": self.observation_cutoff_ms,
            "ingest_time_ms": self.ingest_time_ms,  # None serialises as JSON null
            # FIX02 ? Blocker 5: availability classification
            "availability_kind": self.availability_kind.value,
        }, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(payload.encode()).hexdigest()

    def stable_key(self) -> str:
        return f"{self.symbol}:{self.interval}:{self.bar_open}"

    def verify_checksum(self) -> bool:
        return self.checksum == self._compute_checksum()


# ---------------------------------------------------------------------------
# Manifest + Dataset version
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class DatasetManifest:
    """
    Frozen (immutable) manifest bound to one dataset version.

    Integrity chain
    ---------------
    ``manifest_hash``
        SHA-256 of all bar checksums concatenated in bar_open order.
        Detects any change in bar OHLCV / provenance / temporal fields.
    ``manifest_integrity_hash``
        SHA-256 of a canonical JSON covering ALL manifest metadata fields ?
        including gap_bar_opens, duplicate_count, non_final_count, created_at_ms
        and source_hash (FIX02) ? plus manifest_hash.
        Detects tampering with manifest metadata even when bar content is intact.

    FIX01 ? Gap 2
    -------------
    * frozen=True prevents any in-place mutation by callers.
    * manifest_integrity_hash covers all metadata ? adversarial field edits are
      detectable via verify_integrity().
    * register() and correct() use dataclasses.replace() instead of direct
      field mutation; each replace() triggers __post_init__ which recomputes
      manifest_integrity_hash to reflect the updated fields.

    FIX02 ? Blocker 2
    -----------------
    * gap_bar_opens changed to Tuple[int, ...] ? the frozen dataclass cannot
      prevent mutation of a List's contents; a tuple is truly immutable.
      __post_init__ normalises any list input to a tuple before hashing.
    * _compute_integrity_hash now covers gap_bar_opens, duplicate_count,
      non_final_count, and created_at_ms ? previously omitted, allowing a
      partial-coverage or stale manifest to pass integrity verification.

    FIX02 ? Blocker 6
    -----------------
    * source_hash: Optional[str] added ? SHA-256 of the raw fixture file bytes,
      bound to the manifest at import time and included in the integrity hash.

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
    coverage_pct: float      # 0?100; fraction of expected bars present
    gap_count: int
    # FIX02 ? Blocker 2: Tuple[int, ...] is immutable; List contents are mutable
    # even inside a frozen dataclass.  __post_init__ normalises any list input.
    gap_bar_opens: Tuple[int, ...]
    duplicate_count: int
    non_final_count: int
    manifest_hash: str       # sha256 of all bar checksums in bar_open order
    created_at_ms: int
    parent_version: Optional[int]  # lineage: which version this corrects
    lineage_reason: Optional[str]
    # FIX02 ? Blocker 6: SHA-256 of raw fixture file bytes; None for non-file sources
    source_hash: Optional[str] = None
    # FIX01: manifest-level integrity hash (auto-computed in __post_init__)
    manifest_integrity_hash: str = field(default="", compare=False)
    # FIX03-B: provenance sentinel ? True ONLY when from_dict() found and validated
    # a stored manifest_integrity_hash. Never included in the integrity hash itself
    # or in serialisation (to_dict). Legacy manifests reconstructed without a stored
    # hash have this flag set to False and are rejected at the verified registration
    # boundary (register()).
    provenance_verified: bool = field(default=True, compare=False)

    def __post_init__(self):
        """
        Normalise gap_bar_opens to a tuple, then compute and freeze
        manifest_integrity_hash.

        FIX02 ? Blocker 2: normalisation happens BEFORE hashing so that the
        integrity hash always reflects a canonical tuple representation,
        regardless of whether the caller passed a list or a tuple.
        """
        # Normalise gap_bar_opens to tuple (frozen datac…5733 tokens truncated…s an empty list when no bars are observable at the given cutoff.
        For range-complete guarantees use range_query() with require_complete=True.

        FIX02 ? Blocker 5: require_confirmed_availability added.
        """
        if dataset_id not in self._datasets:
            raise HistoricalDataError(f"Unknown dataset: {dataset_id}")
        v = version if version is not None else self.latest_version(dataset_id)
        bars, _ = self._datasets[dataset_id][v]
        eligible = []
        for bar in bars:
            if (type(bar.observation_cutoff_ms) is not int
                    or type(bar.bar_close) is not int
                    or bar.observation_cutoff_ms < bar.bar_close + 1
                    or (bar.ingest_time_ms is not None
                        and (type(bar.ingest_time_ms) is not int
                             or bar.observation_cutoff_ms < bar.ingest_time_ms))):
                raise HistoricalDataError(
                    f"Invalid point-in-time availability for {bar.stable_key()}"
                )
            if not bar.verify_checksum():
                raise HistoricalDataError(
                    f"Bar checksum failure in dataset {dataset_id}: {bar.stable_key()}"
                )
            if bar.observation_cutoff_ms <= decision_cutoff_ms:
                eligible.append(bar)
        if require_confirmed_availability:
            eligible = [
                b for b in eligible
                if b.availability_kind == DataAvailabilityKind.CONFIRMED
            ]
        return sorted(eligible, key=lambda b: b.bar_open)

    def range_query(
        self,
        dataset_id: str,
        start_ms: int,
        end_ms: int,
        decision_cutoff_ms: int,
        *,
        version: Optional[int] = None,
        require_complete: bool = True,
        require_confirmed_availability: bool = False,
    ) -> List[HistoricalBar]:
        """
        Return bars in [start_ms, end_ms] observable at decision_cutoff_ms.

        FIX01 ? Gap 4: fail-closed by default (require_complete=True).
        When require_complete is True, raises HistoricalDataError if the
        returned bars do not form a complete contiguous sequence covering
        [start_ms, end_ms] with no gaps.  This prevents silent partial
        backtests.

        ``require_confirmed_availability``
            Forwarded to snapshot(): when True, RETROSPECTIVE bars are excluded
            before the completeness check.  A dataset that contains only
            RETROSPECTIVE bars with this flag set will fail as incomplete.

        Set require_complete=False only when explicitly handling partial data.
        Raises if no bars qualify at all regardless of require_complete.

        FIX02 ? Blocker 5: require_confirmed_availability added.
        """
        all_bars = self.snapshot(
            dataset_id, decision_cutoff_ms, version=version,
            require_confirmed_availability=require_confirmed_availability,
        )
        result = [b for b in all_bars if start_ms <= b.bar_open <= end_ms]
        if not result:
            raise HistoricalDataError(
                f"No eligible bars in [{start_ms}, {end_ms}] "
                f"at cutoff {decision_cutoff_ms} for {dataset_id}"
            )

        if require_complete:
            manifest = self.get_manifest(dataset_id, version)
            interval_ms = _interval_to_ms(manifest.interval)
            actual_opens = {b.bar_open for b in result}
            missing = []
            cur = start_ms
            while cur <= end_ms:
                if cur not in actual_opens:
                    missing.append(cur)
                cur += interval_ms
            if missing:
                raise HistoricalDataError(
                    f"Incomplete range [{start_ms}, {end_ms}]: "
                    f"{len(missing)} bar(s) missing or not yet observable "
                    f"at cutoff {decision_cutoff_ms} "
                    f"(first missing bar_open: {missing[0]}). "
                    "Use require_complete=False for partial reads."
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

        FIX01: uses dataclasses.replace() to update frozen manifest fields;
        manifest_integrity_hash is recomputed automatically via __post_init__.
        """
        base_v = base_version if base_version is not None else self.latest_version(dataset_id)
        _, base_manifest = self._datasets[dataset_id][base_v]

        validated, new_manifest = validate_bars(
            new_bars, base_manifest.symbol, base_manifest.interval, allow_gaps=allow_gaps
        )
        # Update version, lineage, and copy inherited metadata from base
        new_manifest = dataclasses.replace(
            new_manifest,
            version=base_v + 1,
            parent_version=base_v,
            lineage_reason=reason,
            exchange=base_manifest.exchange,
            market=base_manifest.market,
            source_label=base_manifest.source_label,
        )

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

    The fast producer (real-time pipeline) calls ``enqueue(bar)`` ? never blocks.
    A background worker drains the queue and calls ``_write_one(bar)``.
    Write failures and backpressure are isolated from the producer.

    Design:
    - Producer: ``enqueue()`` ? puts to bounded queue, drops on full (backpressure).
    - Worker: ``_drain_loop()`` ? reads from queue, calls ``_write_one()``.
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
        NEVER raises ? producer must not be interrupted by archive failures.
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
    availability_kind: DataAvailabilityKind = DataAvailabilityKind.CONFIRMED,
) -> HistoricalBar:
    """
    Create a synthetic test bar.

    FIX02 ? Blocker 5: availability_kind parameter added (default CONFIRMED)
    so that test helpers can produce RETROSPECTIVE bars where needed.
    """
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
        availability_kind=availability_kind,
    )


# ---------------------------------------------------------------------------
# FIX03-A ? Custody-grade access adapter
# ---------------------------------------------------------------------------

class CustodyAccessor:
    """
    Custody-grade access adapter for HistoricalLibrary.

    Research callers that require confirmed-evidence guarantees MUST obtain
    data through this adapter rather than calling HistoricalLibrary.snapshot()
    or HistoricalLibrary.range_query() directly.

    ``require_confirmed_availability=True`` is ALWAYS enforced, unconditionally.
    Callers cannot accidentally bypass the gate through argument defaults:
    the parameter is not exposed on CustodyAccessor's public API.

    For exploratory research where RETROSPECTIVE bars are acceptable, use the
    underlying HistoricalLibrary methods directly and document the choice.

    FIX03-A: this adapter is the required answer to the architectural gap in
    which callers could forget to pass require_confirmed_availability=True and
    silently receive RETROSPECTIVE bars in confirmed-evidence research workflows.
    """

    def __init__(self, library: "HistoricalLibrary") -> None:
        self._library = library

    def snapshot(
        self,
        dataset_id: str,
        decision_cutoff_ms: int,
        *,
        version: Optional[int] = None,
    ) -> "List[HistoricalBar]":
        """
        Return bars observable at ``decision_cutoff_ms`` with confirmed
        availability.  RETROSPECTIVE bars are always excluded.
        Cannot be bypassed by caller defaults.
        """
        return self._library.snapshot(
            dataset_id,
            decision_cutoff_ms,
            version=version,
            require_confirmed_availability=True,  # non-negotiable custody contract
        )

    def range_query(
        self,
        dataset_id: str,
        start_ms: int,
        end_ms: int,
        decision_cutoff_ms: int,
        *,
        version: Optional[int] = None,
        require_complete: bool = True,
    ) -> "List[HistoricalBar]":
        """
        Return bars in [start_ms, end_ms] with confirmed availability.
        RETROSPECTIVE bars are always excluded before the completeness check.
        Cannot be bypassed by caller defaults.
        """
        return self._library.range_query(
            dataset_id,
            start_ms,
            end_ms,
            decision_cutoff_ms,
            version=version,
            require_complete=require_complete,
            require_confirmed_availability=True,  # non-negotiable custody contract
        )


def make_fixture_csv(bars: List[HistoricalBar]) -> str:
    """Return CSV string for use in tests (no header)."""
    lines = []
    for b in bars:
        lines.append(
            f"{b.bar_open},{b.bar_close},{b.open},{b.high},{b.low},{b.close},{b.volume}"
        )
    return "\n".join(lines)

