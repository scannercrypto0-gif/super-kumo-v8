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
* Full integrity chain — bar checksums cover all provenance fields including
  observation_cutoff_ms and source_label; manifest integrity hash covers all
  manifest metadata + the bar-level manifest_hash.
* Import confinement — symlink rejection, raw-string traversal guard, and
  optional trusted_root boundary enforcement.
* Fail-closed range queries — range_query verifies complete contiguous coverage
  by default; partial reads are opt-in via require_complete=False.

No live exchange calls, no credentials, no G1 pipeline coupling.

SF-DATA-01-FIX01 (Issue #50) changes vs original SF-DATA-01:
  - HistoricalBar._compute_checksum: adds observation_cutoff_ms, ingest_time_ms,
    source_label to SHA-256 payload (Gap 1)
  - DatasetManifest: frozen=True + manifest_integrity_hash field covering all
    metadata + manifest_hash; verify_integrity() method (Gap 2)
  - register() / correct(): use dataclasses.replace() — no direct field mutation
    on frozen instances (Gap 2)
  - import_fixture_csv: raw-string guard BEFORE resolve(), symlink rejection,
    optional trusted_root parameter (Gap 3)
  - range_query: require_complete=True default; raises on partial coverage (Gap 4)

SF-DATA-01-FIX02 (Issue #50 owner review 2026-10-23) changes vs FIX01:
  - Blocker 1: CI workflow updated to include test_sf_data_01.py in discovery
  - Blocker 2: DatasetManifest.gap_bar_opens: List→Tuple[int,...]; integrity hash
    now covers gap_bar_opens, duplicate_count, non_final_count, created_at_ms
  - Blocker 3: register() validates bar checksums, manifest_hash, integrity_hash;
    from_dict() validates stored hash against recomputed (no silent laundering)
  - Blocker 4: validate_bars() checks math.isfinite, positive prices, nonneg
    volume, and OHLC ordering (high≥max(O,C,L); low≤min(O,C,H))
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

    FIX02 — Blocker 5
    -----------------
    RETROSPECTIVE
        Bar was imported from a historical fixture; the actual receipt time is
        unknown.  ``observation_cutoff_ms = bar_close + 1`` is a theoretical
        lower bound — the bar *could not* have been known before bar close, but
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
        ``None`` if unknown — the historical receipt time is not fabricated.

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
    # FIX02 — Blocker 5: distinguishes theoretical (fixture) from recorded timestamps
    availability_kind: DataAvailabilityKind = DataAvailabilityKind.CONFIRMED
    checksum: str = field(default="", compare=False)

    def __post_init__(self):
        # recompute and store checksum (dataclass is frozen so we use object.__setattr__)
        cs = self._compute_checksum()
        object.__setattr__(self, "checksum", cs)

    def _compute_checksum(self) -> str:
        """
        SHA-256 over canonical JSON covering all OHLCV + provenance + temporal
        + availability fields.

        FIX01 — Gap 1: observation_cutoff_ms, ingest_time_ms and source_label
        are included so that any tamper of these fields is detectable.

        FIX02 — Blocker 5: availability_kind is included so that a RETROSPECTIVE
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
            # FIX01 additions — provenance completeness
            "source_label": self.source_label,
            "observation_cutoff_ms": self.observation_cutoff_ms,
            "ingest_time_ms": self.ingest_time_ms,  # None serialises as JSON null
            # FIX02 — Blocker 5: availability classification
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
        SHA-256 of a canonical JSON covering ALL manifest metadata fields —
        including gap_bar_opens, duplicate_count, non_final_count, created_at_ms
        and source_hash (FIX02) — plus manifest_hash.
        Detects tampering with manifest metadata even when bar content is intact.

    FIX01 — Gap 2
    -------------
    * frozen=True prevents any in-place mutation by callers.
    * manifest_integrity_hash covers all metadata — adversarial field edits are
      detectable via verify_integrity().
    * register() and correct() use dataclasses.replace() instead of direct
      field mutation; each replace() triggers __post_init__ which recomputes
      manifest_integrity_hash to reflect the updated fields.

    FIX02 — Blocker 2
    -----------------
    * gap_bar_opens changed to Tuple[int, ...] — the frozen dataclass cannot
      prevent mutation of a List's contents; a tuple is truly immutable.
      __post_init__ normalises any list input to a tuple before hashing.
    * _compute_integrity_hash now covers gap_bar_opens, duplicate_count,
      non_final_count, and created_at_ms — previously omitted, allowing a
      partial-coverage or stale manifest to pass integrity verification.

    FIX02 — Blocker 6
    -----------------
    * source_hash: Optional[str] added — SHA-256 of the raw fixture file bytes,
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
    coverage_pct: float      # 0–100; fraction of expected bars present
    gap_count: int
    # FIX02 — Blocker 2: Tuple[int, ...] is immutable; List contents are mutable
    # even inside a frozen dataclass.  __post_init__ normalises any list input.
    gap_bar_opens: Tuple[int, ...]
    duplicate_count: int
    non_final_count: int
    manifest_hash: str       # sha256 of all bar checksums in bar_open order
    created_at_ms: int
    parent_version: Optional[int]  # lineage: which version this corrects
    lineage_reason: Optional[str]
    # FIX02 — Blocker 6: SHA-256 of raw fixture file bytes; None for non-file sources
    source_hash: Optional[str] = None
    # FIX01: manifest-level integrity hash (auto-computed in __post_init__)
    manifest_integrity_hash: str = field(default="", compare=False)

    def __post_init__(self):
        """
        Normalise gap_bar_opens to a tuple, then compute and freeze
        manifest_integrity_hash.

        FIX02 — Blocker 2: normalisation happens BEFORE hashing so that the
        integrity hash always reflects a canonical tuple representation,
        regardless of whether the caller passed a list or a tuple.
        """
        # Normalise gap_bar_opens to tuple (frozen dataclass cannot prevent
        # mutation of a list's *contents*, but a tuple is truly immutable)
        gbo = self.gap_bar_opens
        if not isinstance(gbo, tuple):
            object.__setattr__(self, "gap_bar_opens", tuple(gbo))
        ih = self._compute_integrity_hash()
        object.__setattr__(self, "manifest_integrity_hash", ih)

    def _compute_integrity_hash(self) -> str:
        """
        SHA-256 over canonical JSON of ALL manifest metadata + manifest_hash.
        Does NOT include manifest_integrity_hash itself (avoids circularity).

        FIX02 — Blocker 2: gap_bar_opens, duplicate_count, non_final_count and
        created_at_ms were previously omitted, allowing a partial-coverage
        manifest or one with stale timestamps to pass verification.  They are
        now included.

        FIX02 — Blocker 6: source_hash included so fixture-file provenance is
        part of the integrity chain.
        """
        payload = json.dumps({
            "dataset_id": self.dataset_id,
            "version": self.version,
            "exchange": self.exchange,
            "market": self.market,
            "symbol": self.symbol,
            "interval": self.interval,
            "timezone": self.timezone,
            "source_label": self.source_label,
            "bar_count": self.bar_count,
            "min_bar_open": self.min_bar_open,
            "max_bar_open": self.max_bar_open,
            "coverage_pct": self.coverage_pct,
            "gap_count": self.gap_count,
            # FIX02 — Blocker 2: previously omitted fields
            "gap_bar_opens": list(self.gap_bar_opens),  # canonical list for JSON
            "duplicate_count": self.duplicate_count,
            "non_final_count": self.non_final_count,
            "created_at_ms": self.created_at_ms,
            "parent_version": self.parent_version,
            "lineage_reason": self.lineage_reason,
            # FIX02 — Blocker 6: fixture file provenance
            "source_hash": self.source_hash,
            "manifest_hash": self.manifest_hash,
        }, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(payload.encode()).hexdigest()

    def verify_integrity(self) -> bool:
        """
        Return True if manifest_integrity_hash matches a recomputation from
        the stored fields.  A False result indicates metadata tampering.
        """
        return self.manifest_integrity_hash == self._compute_integrity_hash()

    def verify_hash(self, bars: Sequence[HistoricalBar]) -> bool:
        """Recompute manifest_hash from bars and compare."""
        sorted_bars = sorted(bars, key=lambda b: b.bar_open)
        combined = "".join(b.checksum for b in sorted_bars)
        expected = hashlib.sha256(combined.encode()).hexdigest()
        return self.manifest_hash == expected

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "DatasetManifest":
        """
        Reconstruct a DatasetManifest from a dict (e.g. from JSON serialisation).

        FIX02 — Blocker 3: the previous implementation silently discarded the
        stored ``manifest_integrity_hash`` and recomputed it from the fields.
        This launders a tampered record: an adversary who modifies both a field
        AND the stored hash to match would produce a "valid" manifest.

        The corrected implementation:
        1. Pops the stored hash (to avoid passing it to __init__).
        2. Normalises gap_bar_opens from a JSON list to a tuple.
        3. Constructs the object (which recomputes the hash in __post_init__).
        4. Validates that the STORED hash matches the RECOMPUTED hash.
           If they differ the record has been tampered → raises HistoricalDataError.

        If the stored dict has no manifest_integrity_hash (e.g. legacy record)
        the validation step is skipped and the computed hash is accepted.
        """
        d = dict(d)
        stored_ih = d.pop("manifest_integrity_hash", None)
        # Normalise gap_bar_opens: JSON arrays deserialise as lists; we need tuples
        if "gap_bar_opens" in d and isinstance(d["gap_bar_opens"], list):
            d["gap_bar_opens"] = tuple(d["gap_bar_opens"])
        obj = cls(**d)
        # Validate stored hash against freshly recomputed hash
        if stored_ih is not None and obj.manifest_integrity_hash != stored_ih:
            raise HistoricalDataError(
                "manifest_integrity_hash mismatch on from_dict: "
                "stored hash does not match recomputed value — record may have been tampered"
            )
        return obj


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
        # FIX02 — Blocker 4: OHLCV numeric validity checks
        for fname, fval in (
            ("open", bar.open), ("high", bar.high),
            ("low", bar.low), ("close", bar.close), ("volume", bar.volume),
        ):
            if not math.isfinite(fval):
                raise HistoricalDataError(
                    f"Non-finite {fname} at bar_open={bar.bar_open}: {fval!r}"
                )
        if bar.open <= 0 or bar.high <= 0 or bar.low <= 0 or bar.close <= 0:
            raise HistoricalDataError(
                f"Non-positive price at bar_open={bar.bar_open}: "
                f"O={bar.open} H={bar.high} L={bar.low} C={bar.close}"
            )
        if bar.volume < 0:
            raise HistoricalDataError(
                f"Negative volume at bar_open={bar.bar_open}: {bar.volume!r}"
            )
        if bar.high < max(bar.open, bar.close, bar.low):
            raise HistoricalDataError(
                f"OHLC violation at bar_open={bar.bar_open}: "
                f"high={bar.high} < max(open={bar.open}, close={bar.close}, low={bar.low})"
            )
        if bar.low > min(bar.open, bar.close, bar.high):
            raise HistoricalDataError(
                f"OHLC violation at bar_open={bar.bar_open}: "
                f"low={bar.low} > min(open={bar.open}, close={bar.close}, high={bar.high})"
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
        dataset_id="",         # caller fills in via dataclasses.replace()
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
    trusted_root: Optional[Path | str] = None,
) -> Tuple[List[HistoricalBar], DatasetManifest]:
    """
    Import OHLCV bars from a CSV fixture file.

    Expected columns (in order, no header required):
        bar_open, bar_close, open, high, low, close, volume

    All values numeric; bar_open / bar_close are epoch-ms integers.
    Source bytes are hashed but not embedded; credentials are never recorded.

    FIX01 — Gap 3: import confinement
    ----------------------------------
    1. Raw-string ``..`` guard applied BEFORE Path.resolve() so the check is
       not silently bypassed (resolved paths never contain ``..``).
    2. Symlink rejection: the path must not be a symlink before resolving.
    3. ``trusted_root``: if supplied, the resolved path must be a descendant;
       rejects both parent-escape and symlink-to-outside-root patterns.

    Raises HistoricalDataError on schema or ordering violations.
    Raises ValueError on path traversal, symlink, or confinement violations.
    """
    raw_str = str(path)

    # FIX01 Guard 1: check raw string BEFORE resolving (resolve() erases "..")
    if ".." in raw_str:
        raise ValueError(f"Path traversal detected in: {path!r}")

    raw_path = Path(path)

    # FIX01 Guard 2: reject symlinks before following them
    if raw_path.is_symlink():
        raise ValueError(f"Symlink not allowed as fixture path: {path!r}")

    resolved = raw_path.resolve()

    # FIX01 Guard 3: optional trusted_root confinement
    if trusted_root is not None:
        trusted = Path(trusted_root).resolve()
        try:
            resolved.relative_to(trusted)
        except ValueError:
            raise ValueError(
                f"Fixture path {resolved!r} escapes trusted root {trusted!r}"
            )

    if not resolved.is_file():
        raise HistoricalDataError(f"Fixture not found: {resolved}")

    # FIX02 — Blocker 6: read bytes ONCE; hash them; parse via StringIO.
    # Previous code called read_bytes() for hashing then opened the file
    # again for parsing — two separate reads, which could theoretically
    # diverge on a replaced file.  A single read guarantees the hash and
    # the parsed bars correspond to exactly the same bytes.
    file_bytes = resolved.read_bytes()
    source_hash = hashlib.sha256(file_bytes).hexdigest()

    interval_ms = _interval_to_ms(interval)
    bars: List[HistoricalBar] = []

    reader = csv.reader(io.StringIO(file_bytes.decode("utf-8")))
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
            ingest_time_ms=None,          # receipt time unknown for historical fixtures
            # FIX02 — Blocker 5: fixture bars are RETROSPECTIVE — bar_close+1 is a
            # theoretical lower bound, not a confirmed ingestion timestamp
            availability_kind=DataAvailabilityKind.RETROSPECTIVE,
        )
        bars.append(bar)

    validated, manifest = validate_bars(bars, symbol, interval, allow_gaps=allow_gaps)
    # FIX02 — Blocker 6: bind source_hash to manifest so fixture provenance is
    # permanently part of the integrity chain
    manifest = dataclasses.replace(manifest, source_hash=source_hash)
    return validated, manifest


# ---------------------------------------------------------------------------
# Historical snapshot / range access
# ---------------------------------------------------------------------------

@dataclass
class HistoricalLibrary:
    """
    In-memory versioned historical library.

    Versions are immutable (DatasetManifest is frozen). Corrections create a
    new version (``correct()``). All reads are deterministic given the same
    version and decision_cutoff_ms.

    FIX01 — Gap 2: register() and correct() use dataclasses.replace() to
    produce updated frozen DatasetManifest instances instead of direct field
    mutation, which is now rejected by the frozen dataclass.
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
        """
        Store a validated dataset under dataset_id at manifest.version.

        FIX01: if manifest.dataset_id differs from dataset_id, a new frozen
        DatasetManifest instance is produced via dataclasses.replace() (which
        recomputes manifest_integrity_hash to reflect the new dataset_id).
        The caller's manifest reference is never mutated.

        FIX02 — Blocker 3: validate the full integrity chain before storing:
        1. All bar checksums must pass (detect OHLCV/provenance tamper).
        2. manifest.verify_hash(bars) must hold (detect bar-set tamper).
        3. manifest.verify_integrity() must hold (detect metadata tamper).
        """
        # FIX02 — Blocker 3: bar-level checksum validation
        bad_keys = [b.stable_key() for b in bars if not b.verify_checksum()]
        if bad_keys:
            raise HistoricalDataError(
                f"Bar checksum failure(s) for {dataset_id}: {bad_keys[:5]}"
            )
        # FIX02 — Blocker 3: manifest_hash must match the submitted bars
        if not manifest.verify_hash(bars):
            raise HistoricalDataError(
                f"manifest_hash does not match bars for {dataset_id} "
                f"v{manifest.version}"
            )
        # FIX02 — Blocker 3: manifest_integrity_hash must be self-consistent
        if not manifest.verify_integrity():
            raise HistoricalDataError(
                f"manifest_integrity_hash invalid for {dataset_id} "
                f"v{manifest.version}"
            )
        if manifest.dataset_id != dataset_id:
            manifest = dataclasses.replace(manifest, dataset_id=dataset_id)
            # After replace(), re-verify integrity (dataset_id is now different)
            if not manifest.verify_integrity():
                raise HistoricalDataError(
                    f"manifest_integrity_hash invalid after dataset_id update "
                    f"for {dataset_id}"
                )
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
        """
        Return the manifest for dataset_id at version (default: latest).

        FIX01: DatasetManifest is frozen, so the returned reference is already
        immutable — callers cannot alter registered version metadata.
        """
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
        require_confirmed_availability: bool = False,
    ) -> List[HistoricalBar]:
        """
        Return all bars observable at ``decision_cutoff_ms`` (point-in-time).

        Bars with observation_cutoff_ms > decision_cutoff_ms are excluded,
        preventing future-bar leakage into research decisions.

        ``require_confirmed_availability``
            When True, also excludes RETROSPECTIVE bars (fixtures whose
            observation timestamp is a theoretical lower bound, not an actual
            ingestion time).  Use this when the research requires a provably
            confirmed ingest time for every bar.

        Returns an empty list when no bars are observable at the given cutoff.
        For range-complete guarantees use range_query() with require_complete=True.

        FIX02 — Blocker 5: require_confirmed_availability added.
        """
        if dataset_id not in self._datasets:
            raise HistoricalDataError(f"Unknown dataset: {dataset_id}")
        v = version if version is not None else self.latest_version(dataset_id)
        bars, _ = self._datasets[dataset_id][v]
        eligible = [b for b in bars if b.observation_cutoff_ms <= decision_cutoff_ms]
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

        FIX01 — Gap 4: fail-closed by default (require_complete=True).
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

        FIX02 — Blocker 5: require_confirmed_availability added.
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
    availability_kind: DataAvailabilityKind = DataAvailabilityKind.CONFIRMED,
) -> HistoricalBar:
    """
    Create a synthetic test bar.

    FIX02 — Blocker 5: availability_kind parameter added (default CONFIRMED)
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


def make_fixture_csv(bars: List[HistoricalBar]) -> str:
    """Return CSV string for use in tests (no header)."""
    lines = []
    for b in bars:
        lines.append(
            f"{b.bar_open},{b.bar_close},{b.open},{b.high},{b.low},{b.close},{b.volume}"
        )
    return "\n".join(lines)
