"""C1 — Owner-supplied BTCUSDT Spot 15m source interface with NON_PIT integrity.

Canonical contract: aql.p0.historical-decision.v1
Research only. No live ingestion, no PIT claims, no 1m aggregation.

Governed by:
  Core #180 comment 6540382460 — canonical v1 spec
  Core #180 comment 6540572768 — C1 execution task
  PM #202 comment 6540571630  — bounded implementation authorization

RETROSPECTIVE_NON_PIT: receipt_ms=null, known_at_ms=null, availability_kind=RETROSPECTIVE.
observation_lower_bound_ms = bar_close_ms+1 is ONLY a theoretical lower bound, NOT a
certified known-at timestamp.

Fail closed on:
  - Missing or wrong source bytes SHA-256
  - Wrong interval (must be 900000 ms = 15m)
  - Non-final bars, grid gaps, duplicates
  - Mismatched bar count (must be exactly 672)
  - Future bars relative to declared window
  - Wrong symbol/market/exchange
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from hashlib import sha256
from typing import Any

# ---------------------------------------------------------------------------
# Constants frozen by canonical spec
# ---------------------------------------------------------------------------

SCHEMA = "aql.p0.historical-decision.v1"
PROJECT_ID = "AQL-CRYPTO-RESEARCH-001"
EXCHANGE = "BINANCE"
MARKET = "SPOT"
SYMBOL = "BTCUSDT"
INTERVAL_MS = 900_000          # 15 minutes exactly
WINDOW_START_MS = 1_704_067_200_000    # 2024-01-01 00:00:00 UTC
WINDOW_END_EXCLUSIVE_MS = 1_704_672_000_000  # 2024-01-08 00:00:00 UTC
EXPECTED_BAR_COUNT = 672       # (7 days * 24 h * 4 bars/h)
MODE = "RETROSPECTIVE_NON_PIT"
RESEARCH_ONLY = True

# Owner-supplied exact byte hashes (verified by Factory comment 6540521965)
# The outer ZIP and manifest are the owner's delivery package. The NORMALIZED
# JSON is what C1 validates for bar-level decisions.
# NOTE: The outer ZIP SHA in Factory comment uses the TWO-FILE package;
# Core C1 works from the NORMALIZED JSON form for bar-level decisions.
# Reverify all hashes in executor environment — do not trust ambient state.

# Hash domain map (Factory #77 comment 6540521965 — three distinct commitments):
#   OUTER_ZIP_SHA256  : SHA-256 of the owner's delivery ZIP package
#   MANIFEST_SHA256   : SHA-256 of manifest.json inside the ZIP
#   NORMALIZED_SHA256 : SHA-256 of the normalized JSON (bar-level decision input, validated here)
OUTER_ZIP_SHA256 = "f4e0b3680dd56c9fbe680be2473b8de29fc1d8d7e22657973c85945d2bf99f97"
MANIFEST_SHA256 = "f731bc19c1d4bb0dfa79198c6739a4dbd356e02904086d4df2a136773bd25456"
NORMALIZED_SHA256 = "a881cc99e80697f2da57784b5bea91a7f339c6c391d4d53cc0222842168af0f0"
# CONTRACT FIELD source_bytes_sha256 = OUTER_ZIP_SHA256 (identifies the full owner package)
SOURCE_BYTES_SHA256 = OUTER_ZIP_SHA256
RECEIPT_STATUS = "MISSING_UNATTESTED"   # No independently observed receipt; null in contract
RECEIPT_MISSING_REASON = "Binance publisher checksum files establish byte integrity only; no independently recorded historical-arrival timestamp is available for the original ZIP delivery."
CUSTODY_STATUS = "LOCAL_VERIFIED_NON_INDEPENDENT"

# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------

class C1SourceRejected(ValueError):
    """Fatal: source does not meet NON_PIT integrity requirements. Fail closed."""


@dataclass(frozen=True)
class P0Bar:
    """One immutable 15m bar as delivered by C1 to C2/Factory."""
    bar_id: str             # "BTCUSDT:15m:<bar_open_ms>"
    bar_open_ms: int
    bar_close_ms: int       # bar_open_ms + 899_999
    open: float
    high: float
    low: float
    close: float
    volume: float
    is_final: bool          # always True for historical delivery
    source_label: str
    availability_kind: str  # always "RETROSPECTIVE"
    available_as_of_decision: str  # always "UNKNOWN"
    observation_lower_bound_ms: int  # bar_close_ms + 1 — THEORETICAL LOWER BOUND ONLY
    receipt_ms: None        # always null: no observed receipt
    known_at_ms: None       # always null: no PIT evidence
    bar_checksum: str       # SHA-256 of canonical bar record
    gap_state: str          # "COMPLETE" | "MISSING" | "UNKNOWN"
    correction_generation_id: str
    correction_parent_id: None  # not attested


@dataclass(frozen=True)
class P0SourceManifest:
    """Run manifest fragment owned by C1 (hashes and data lineage)."""
    schema: str
    project_id: str
    exchange: str
    market: str
    symbol: str
    interval_ms: int
    timezone: str
    dataset_id: str
    dataset_version: int
    raw_generation_id: str
    source_bytes_sha256: str
    source_provider: str
    source_version: str
    source_receipt_sha256: None   # null — receipt not independently attested
    receipt_status: str
    receipt_missing_reason: str
    custody_status: str
    manifest_integrity_sha256: str
    ordered_bar_checksums_sha256: str
    gap_inventory_sha256: str
    correction_lineage_sha256: str
    window_start_ms: int
    window_end_exclusive_ms: int
    mode: str
    research_only: bool
    bars: tuple[P0Bar, ...]


# ---------------------------------------------------------------------------
# Canonical helpers (matching spec: UTF-8 JSON sorted keys compact)
# ---------------------------------------------------------------------------

def _canonical_bytes(obj: Any) -> bytes:
    return json.dumps(
        obj,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def _sha256_hex(data: bytes) -> str:
    return sha256(data).hexdigest()


def _bar_checksum(bar_open_ms: int, o: float, h: float, l: float, c: float, v: float) -> str:
    """Deterministic per-bar checksum over OHLCV matching canonical spec."""
    rec = {"bar_open_ms": bar_open_ms, "close": c, "high": h, "low": l, "open": o, "volume": v}
    return _sha256_hex(_canonical_bytes(rec))


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def _validate_bar_row(row: Any, index: int, expected_open_ms: int) -> tuple:
    """Parse and validate one normalized 15m bar entry [open_ms, close_ms, o, h, l, c, v].
    Returns (open_ms, close_ms, o, h, l, c, v).
    Raises C1SourceRejected on any violation.
    """
    if not isinstance(row, list) or len(row) != 7:
        raise C1SourceRejected(f"BAR_{index}_INVALID_SHAPE: expected 7-element list")
    open_ms, close_ms = row[0], row[1]
    o, h, l, c, v = row[2], row[3], row[4], row[5], row[6]

    if not isinstance(open_ms, int):
        raise C1SourceRejected(f"BAR_{index}_OPEN_MS_NOT_INT")
    if not isinstance(close_ms, int):
        raise C1SourceRejected(f"BAR_{index}_CLOSE_MS_NOT_INT")
    if open_ms != expected_open_ms:
        raise C1SourceRejected(
            f"BAR_{index}_GRID_VIOLATION: expected open {expected_open_ms} got {open_ms}"
        )
    if close_ms != open_ms + INTERVAL_MS - 1:
        raise C1SourceRejected(
            f"BAR_{index}_CLOSE_MS_MISMATCH: expected {open_ms + INTERVAL_MS - 1} got {close_ms}"
        )
    for name, val in (("open", o), ("high", h), ("low", l), ("close", c)):
        if not isinstance(val, (int, float)) or not math.isfinite(val) or val <= 0:
            raise C1SourceRejected(f"BAR_{index}_{name.upper()}_INVALID: {val!r}")
    if not isinstance(v, (int, float)) or not math.isfinite(v) or v < 0:
        raise C1SourceRejected(f"BAR_{index}_VOLUME_INVALID: {v!r}")
    if h < max(o, c):
        raise C1SourceRejected(f"BAR_{index}_HIGH_BELOW_OHLC")
    if l > min(o, c):
        raise C1SourceRejected(f"BAR_{index}_LOW_ABOVE_OHLC")
    return int(open_ms), int(close_ms), float(o), float(h), float(l), float(c), float(v)


@dataclass(frozen=True)
class AdmittedSource:
    """Typed proof that admit_source() passed all three SHA-256 gates.

    load_source() requires this object as a mandatory parameter — it is the
    ONLY way to obtain a P0SourceManifest in production.  Test code may
    construct one directly ONLY for bar-level unit tests that need to bypass
    the hash gate; that bypass must be clearly labelled in the test.

    Fields
    ------
    normalized_bytes:
        The raw normalized JSON bytes that passed the NORMALIZED_SHA256 gate.
    manifest_integrity_sha256:
        The verified hash of manifest.json — carried through to the manifest.
    outer_zip_sha256_verified:
        The outer ZIP hash that matched OUTER_ZIP_SHA256 (audit trail only).
    """
    normalized_bytes: bytes
    manifest_integrity_sha256: str   # verified against MANIFEST_SHA256
    outer_zip_sha256_verified: str   # the hash that matched OUTER_ZIP_SHA256


def admit_source(
    *,
    outer_zip_bytes: bytes | None,
    manifest_bytes: bytes | None,
    normalized_bytes: bytes,
) -> AdmittedSource:
    """Fail-closed source admission boundary.

    MUST be called in any production path before load_source().
    Computes SHA-256 of each argument and compares to the frozen owner pins.

    Parameters
    ----------
    outer_zip_bytes:
        Raw bytes of the owner's delivery ZIP package.
        Must not be None; must hash to OUTER_ZIP_SHA256.
    manifest_bytes:
        Raw bytes of manifest.json extracted from the ZIP.
        Must not be None; must hash to MANIFEST_SHA256.
    normalized_bytes:
        Raw bytes of the normalized JSON (the input to load_source).
        Must hash to NORMALIZED_SHA256.

    Raises
    ------
    C1SourceRejected
        "BLOCKED_REAL_SOURCE: ..." when any argument is None (owner package
        not available in the execution environment).
        "<DOMAIN>_SHA256_MISMATCH: ..." when the actual hash differs from the
        frozen pin — indicates tampered or wrong bytes.
    """
    if outer_zip_bytes is None:
        raise C1SourceRejected(
            "BLOCKED_REAL_SOURCE: outer ZIP bytes not available in environment — "
            "owner must supply the original delivery package"
        )
    if manifest_bytes is None:
        raise C1SourceRejected(
            "BLOCKED_REAL_SOURCE: manifest bytes not available in environment — "
            "owner must supply manifest.json from delivery package"
        )
    # normalized_bytes typed as bytes (not Optional), but guard anyway
    if not isinstance(normalized_bytes, (bytes, bytearray)) or len(normalized_bytes) == 0:
        raise C1SourceRejected(
            "BLOCKED_REAL_SOURCE: normalized_bytes must be non-empty bytes"
        )

    actual_outer = _sha256_hex(outer_zip_bytes)
    if actual_outer != OUTER_ZIP_SHA256:
        raise C1SourceRejected(
            f"OUTER_ZIP_SHA256_MISMATCH: expected {OUTER_ZIP_SHA256!r} "
            f"got {actual_outer!r}"
        )

    actual_manifest = _sha256_hex(manifest_bytes)
    if actual_manifest != MANIFEST_SHA256:
        raise C1SourceRejected(
            f"MANIFEST_SHA256_MISMATCH: expected {MANIFEST_SHA256!r} "
            f"got {actual_manifest!r}"
        )

    actual_normalized = _sha256_hex(normalized_bytes)
    if actual_normalized != NORMALIZED_SHA256:
        raise C1SourceRejected(
            f"NORMALIZED_SHA256_MISMATCH: expected {NORMALIZED_SHA256!r} "
            f"got {actual_normalized!r}"
        )

    # All three gates passed — return typed proof token
    return AdmittedSource(
        normalized_bytes=normalized_bytes,
        manifest_integrity_sha256=actual_manifest,
        outer_zip_sha256_verified=actual_outer,
    )


def _validate_normalized_bars(
    rows: list,
) -> list["P0Bar"]:
    """Private: parse and validate a list of normalized bar rows.

    Extracted so that unit tests can exercise bar-level validation guards
    (grid violations, OHLCV invalidity, count mismatches) using synthetic
    data that bypasses the hash check — via this private helper rather than
    via a public bypass parameter.

    Parameters
    ----------
    rows:
        Already-parsed list of [open_ms, close_ms, o, h, l, c, v] rows,
        exactly EXPECTED_BAR_COUNT of them, grid-aligned from WINDOW_START_MS.

    Returns
    -------
    list[P0Bar]
        Validated P0Bar instances.

    Raises
    ------
    C1SourceRejected
        On any bar-level violation.
    """
    if not isinstance(rows, list):
        raise C1SourceRejected("NORMALIZED_JSON_ROOT_NOT_LIST")
    if len(rows) != EXPECTED_BAR_COUNT:
        raise C1SourceRejected(
            f"BAR_COUNT_MISMATCH: expected {EXPECTED_BAR_COUNT} got {len(rows)}"
        )
    bars: list[P0Bar] = []
    for i, row in enumerate(rows):
        expected_open = WINDOW_START_MS + i * INTERVAL_MS
        open_ms, close_ms, o, h, l, c, v = _validate_bar_row(row, i, expected_open)
        if open_ms >= WINDOW_END_EXCLUSIVE_MS:
            raise C1SourceRejected(f"BAR_{i}_FUTURE_BAR: open_ms {open_ms} >= window end")
        chk = _bar_checksum(open_ms, o, h, l, c, v)
        bars.append(P0Bar(
            bar_id=f"BTCUSDT:15m:{open_ms}",
            bar_open_ms=open_ms,
            bar_close_ms=close_ms,
            open=o, high=h, low=l, close=c, volume=v,
            is_final=True,
            source_label="BINANCE_SPOT_BTCUSDT_15M_OWNER_SUPPLIED",
            availability_kind="RETROSPECTIVE",
            available_as_of_decision="UNKNOWN",
            observation_lower_bound_ms=close_ms + 1,
            receipt_ms=None, known_at_ms=None,
            bar_checksum=chk, gap_state="COMPLETE",
            correction_generation_id="UNKNOWN_NOT_ATTESTED",
            correction_parent_id=None,
        ))
    return bars


def load_source(
    *,
    admitted: AdmittedSource,
    dataset_id: str,
    dataset_version: int = 1,
    raw_generation_id: str = "P0-DEV-2024-01-01-TO-2024-01-08",
    correction_generation_id: str = "UNKNOWN_NOT_ATTESTED",
) -> P0SourceManifest:
    """Load and validate owner-supplied normalized BTCUSDT 15m source.

    PRODUCTION USE: obtain `admitted` from admit_source() which verifies the
    outer ZIP, manifest.json, and normalized bytes against frozen owner pins.
    This is the ONLY sanctioned path to a P0SourceManifest.

    Parameters
    ----------
    admitted:
        Typed proof token returned by admit_source().  This is the ONLY
        valid input path — passing raw bytes directly is not possible.
        Defense-in-depth: load_source() still re-verifies NORMALIZED_SHA256
        on admitted.normalized_bytes before parsing.
    dataset_id:
        Frozen dataset identifier string.
    dataset_version:
        Positive immutable version integer (must be >= 1).
    raw_generation_id:
        Identity string for this frozen input generation.
    correction_generation_id:
        "UNKNOWN_NOT_ATTESTED" — Binance Vision publisher checksums do not
        attest correction history.

    Returns
    -------
    P0SourceManifest
        Validated, immutable source manifest with 672 bars.

    Raises
    ------
    C1SourceRejected
        On any integrity violation. Fail closed.
    """
    if not isinstance(admitted, AdmittedSource):
        raise C1SourceRejected(
            "LOAD_SOURCE_REQUIRES_ADMITTED_SOURCE: call admit_source() first — "
            "bypassing the admission gate is not permitted"
        )

    normalized_json_bytes = admitted.normalized_bytes
    manifest_integrity_sha256 = admitted.manifest_integrity_sha256

    if not isinstance(normalized_json_bytes, (bytes, bytearray)):
        raise C1SourceRejected("NORMALIZED_JSON_MUST_BE_BYTES")
    if not normalized_json_bytes:
        raise C1SourceRejected("NORMALIZED_JSON_EMPTY")

    # --- Defense-in-depth: re-verify hash even though admit_source() already checked ---
    actual_sha = _sha256_hex(normalized_json_bytes)
    if actual_sha != NORMALIZED_SHA256:
        raise C1SourceRejected(
            f"NORMALIZED_SHA256_MISMATCH: expected {NORMALIZED_SHA256!r} got {actual_sha!r}"
        )

    # --- Parse ---
    try:
        rows = json.loads(normalized_json_bytes)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise C1SourceRejected(f"NORMALIZED_JSON_PARSE_ERROR: {exc}") from exc

    # --- Validate dataset identity ---
    if not isinstance(dataset_id, str) or not dataset_id:
        raise C1SourceRejected("DATASET_ID_INVALID")
    if not isinstance(dataset_version, int) or dataset_version < 1:
        raise C1SourceRejected("DATASET_VERSION_INVALID")
    if not isinstance(raw_generation_id, str) or not raw_generation_id:
        raise C1SourceRejected("RAW_GENERATION_ID_INVALID")

    # --- Parse and validate bars (delegates to private helper) ---
    bars = _validate_normalized_bars(rows)

    # Rebuild checksums from validated bars (already computed inside helper)
    checksums: list[str] = [b.bar_checksum for b in bars]

    # Apply correction_generation_id (helper uses a default; patch here if different)
    if correction_generation_id != "UNKNOWN_NOT_ATTESTED":
        bars = [
            P0Bar(
                bar_id=b.bar_id, bar_open_ms=b.bar_open_ms, bar_close_ms=b.bar_close_ms,
                open=b.open, high=b.high, low=b.low, close=b.close, volume=b.volume,
                is_final=b.is_final, source_label=b.source_label,
                availability_kind=b.availability_kind,
                available_as_of_decision=b.available_as_of_decision,
                observation_lower_bound_ms=b.observation_lower_bound_ms,
                receipt_ms=b.receipt_ms, known_at_ms=b.known_at_ms,
                bar_checksum=b.bar_checksum, gap_state=b.gap_state,
                correction_generation_id=correction_generation_id,
                correction_parent_id=b.correction_parent_id,
            )
            for b in bars
        ]

    # --- Verify window coverage ---
    if bars[0].bar_open_ms != WINDOW_START_MS:
        raise C1SourceRejected(
            f"WINDOW_START_MISMATCH: first bar {bars[0].bar_open_ms} != {WINDOW_START_MS}"
        )
    expected_last_open = WINDOW_END_EXCLUSIVE_MS - INTERVAL_MS
    if bars[-1].bar_open_ms != expected_last_open:
        raise C1SourceRejected(
            f"WINDOW_END_MISMATCH: last bar {bars[-1].bar_open_ms} != {expected_last_open}"
        )

    # --- Digest commitments ---
    ordered_bar_checksums_sha256 = _sha256_hex(_canonical_bytes(checksums))

    # Gap inventory: record that all 672 bars are COMPLETE (no gaps detected)
    gap_inventory = {
        "total_scheduled": EXPECTED_BAR_COUNT,
        "complete": EXPECTED_BAR_COUNT,
        "missing": 0,
        "unknown": 0,
        "bars_with_gap_state": [],
    }
    gap_inventory_sha256 = _sha256_hex(_canonical_bytes(gap_inventory))

    # Correction lineage: UNKNOWN_NOT_ATTESTED
    correction_lineage = {
        "status": "UNKNOWN_NOT_ATTESTED",
        "reason": "Publisher checksums establish byte integrity only; correction history not attested.",
        "correction_generation_id": correction_generation_id,
    }
    correction_lineage_sha256 = _sha256_hex(_canonical_bytes(correction_lineage))

    manifest = P0SourceManifest(
        schema=SCHEMA,
        project_id=PROJECT_ID,
        exchange=EXCHANGE,
        market=MARKET,
        symbol=SYMBOL,
        interval_ms=INTERVAL_MS,
        timezone="UTC",
        dataset_id=dataset_id,
        dataset_version=dataset_version,
        raw_generation_id=raw_generation_id,
        source_bytes_sha256=SOURCE_BYTES_SHA256,
        source_provider="BINANCE_VISION",
        source_version="OWNER_SUPPLIED_FIXED_INPUT",
        source_receipt_sha256=None,  # no independently observed receipt
        receipt_status=RECEIPT_STATUS,
        receipt_missing_reason=RECEIPT_MISSING_REASON,
        custody_status=CUSTODY_STATUS,
        manifest_integrity_sha256=manifest_integrity_sha256,
        ordered_bar_checksums_sha256=ordered_bar_checksums_sha256,
        gap_inventory_sha256=gap_inventory_sha256,
        correction_lineage_sha256=correction_lineage_sha256,
        window_start_ms=WINDOW_START_MS,
        window_end_exclusive_ms=WINDOW_END_EXCLUSIVE_MS,
        mode=MODE,
        research_only=RESEARCH_ONLY,
        bars=tuple(bars),
    )
    return manifest
