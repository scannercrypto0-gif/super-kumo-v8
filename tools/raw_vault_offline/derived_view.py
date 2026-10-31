"""
Stage 7 — Offline non-production derived canonical row view.

Rules
-----
- Provenance per row (source digest, normalization version, policy)
- Timestamp precision preserved from source
- Gap/unknown markers propagated — never silently filled
- Same input + policy → same output digest (reproducible)
- Changed correction/policy → new generation (forks, does not mutate)
- Observed event time ≠ source received/available_at (UNKNOWN if unavailable)
- No PIT fabrication
- No modification of C1 or W1 outcome calculations
- Does NOT import from src/aql or research_wp_r0
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Optional

DERIVED_VIEW_POLICY_VERSION = "canonical_ohlcv.v1"


@dataclass
class DerivedRow:
    """One normalised OHLCV row with full provenance."""
    # identity
    instrument: str
    interval: str
    open_time_utc_ms: int          # observed event time
    close_time_utc_ms: int         # exclusive interval end
    # OHLCV
    open: Optional[float]
    high: Optional[float]
    low: Optional[float]
    close: Optional[float]
    volume: Optional[float]
    quote_volume: Optional[float]
    trade_count: Optional[int]
    # provenance
    source_content_sha256: str     # digest of the RAW object this row came from
    source_correction_generation: int
    normalization_policy: str      # DERIVED_VIEW_POLICY_VERSION
    available_at_utc: str          # "UNKNOWN" if source capture time unavailable
    gap_marker: bool = False       # True if this slot exists but data is missing
    unknown_marker: bool = False   # True if provenance is UNKNOWN

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class DerivedViewManifest:
    """Manifest for a derived view generation."""
    view_generation: int
    policy_version: str
    source_content_sha256: str
    source_correction_generation: int
    row_count: int
    output_digest: str             # sha256 of canonical JSON of all rows
    produced_at_utc: str
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


# ── derivation engine ─────────────────────────────────────────────────────────

_REQUIRED_CSV_HEADERS = {
    "open_time", "open", "high", "low", "close", "volume",
    "close_time", "quote_volume", "count",
}

def _parse_float(val: str) -> Optional[float]:
    try:
        return float(val)
    except (ValueError, TypeError):
        return None

def _parse_int(val: str) -> Optional[int]:
    try:
        return int(val)
    except (ValueError, TypeError):
        return None


def derive_view(
    raw_bytes: bytes,
    *,
    source_content_sha256: str,
    source_correction_generation: int = 0,
    instrument: str,
    interval: str,
    available_at_utc: str = "UNKNOWN",
    view_generation: int = 0,
    policy_version: str = DERIVED_VIEW_POLICY_VERSION,
) -> tuple[list[DerivedRow], DerivedViewManifest]:
    """
    Derive a canonical row view from admitted RAW CSV bytes.

    Parameters
    ----------
    raw_bytes                    : original source bytes (CSV)
    source_content_sha256        : content digest of the RAW object
    source_correction_generation : correction generation of the RAW object
    instrument                   : e.g. "BTCUSDT"
    interval                     : e.g. "15m"
    available_at_utc             : "UNKNOWN" if source capture time unavailable
    view_generation              : incremented when policy or correction changes
    policy_version               : normalization policy identifier

    Returns
    -------
    (rows, manifest) — deterministic for same inputs
    """
    rows: list[DerivedRow] = []

    try:
        text = raw_bytes.decode("utf-8")
        reader = csv.DictReader(io.StringIO(text))
        if reader.fieldnames is None:
            raise ValueError("Empty CSV: no headers")
        headers = set(reader.fieldnames)
        missing_cols = _REQUIRED_CSV_HEADERS - headers
        if missing_cols:
            raise ValueError(f"Missing CSV columns: {missing_cols}")

        for csv_row in reader:
            open_ms = _parse_int(csv_row.get("open_time", ""))
            close_ms = _parse_int(csv_row.get("close_time", ""))
            if open_ms is None:
                # unknown slot
                rows.append(DerivedRow(
                    instrument=instrument,
                    interval=interval,
                    open_time_utc_ms=-1,
                    close_time_utc_ms=-1,
                    open=None, high=None, low=None, close=None,
                    volume=None, quote_volume=None, trade_count=None,
                    source_content_sha256=source_content_sha256,
                    source_correction_generation=source_correction_generation,
                    normalization_policy=policy_version,
                    available_at_utc=available_at_utc,
                    gap_marker=False,
                    unknown_marker=True,
                ))
                continue
            rows.append(DerivedRow(
                instrument=instrument,
                interval=interval,
                open_time_utc_ms=open_ms,
                close_time_utc_ms=(close_ms + 1) if close_ms is not None else open_ms + 900_000,
                open=_parse_float(csv_row.get("open", "")),
                high=_parse_float(csv_row.get("high", "")),
                low=_parse_float(csv_row.get("low", "")),
                close=_parse_float(csv_row.get("close", "")),
                volume=_parse_float(csv_row.get("volume", "")),
                quote_volume=_parse_float(csv_row.get("quote_volume", "")),
                trade_count=_parse_int(csv_row.get("count", "")),
                source_content_sha256=source_content_sha256,
                source_correction_generation=source_correction_generation,
                normalization_policy=policy_version,
                available_at_utc=available_at_utc,
                gap_marker=False,
                unknown_marker=False,
            ))
    except Exception as exc:
        # cannot parse: return single unknown-marker row + manifest note
        manifest = DerivedViewManifest(
            view_generation=view_generation,
            policy_version=policy_version,
            source_content_sha256=source_content_sha256,
            source_correction_generation=source_correction_generation,
            row_count=0,
            output_digest="",
            produced_at_utc=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            notes=[f"PARSE_ERROR: {exc}"],
        )
        return [], manifest

    # compute deterministic output digest
    canonical_payload = json.dumps(
        [r.to_dict() for r in rows],
        sort_keys=True, separators=(",", ":"), ensure_ascii=True, default=str,
    ).encode("utf-8")
    output_digest = hashlib.sha256(canonical_payload).hexdigest()

    manifest = DerivedViewManifest(
        view_generation=view_generation,
        policy_version=policy_version,
        source_content_sha256=source_content_sha256,
        source_correction_generation=source_correction_generation,
        row_count=len(rows),
        output_digest=output_digest,
        produced_at_utc=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    )
    return rows, manifest
