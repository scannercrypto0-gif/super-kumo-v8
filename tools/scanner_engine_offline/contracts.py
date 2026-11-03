"""G1 — Immutable PIT input/admission contracts and output envelope.

All timestamps are timezone-aware UTC.  No future data may enter a decision
snapshot: bars with close_at > cutoff_at are excluded before any feature is
computed (fail-closed PIT enforcement).

ScannerNominationEnvelope is the typed output contract — content-addressed
via SHA-256 of canonical sorted-key JSON bytes.

AVAILABILITY CLASSES
  LIVE_PIT             — real receipt timestamps; cutoff ≥ bar.available_at
  RETROSPECTIVE_NON_PIT — historical/synthetic; receipt timestamps not trustworthy
  UNKNOWN              — availability class cannot be determined

CANDIDATE LIFECYCLE
  DISCOVERED → SCREENED → QUALIFIED → NOMINATED
  Terminal: REJECTED | EXPIRED | UNKNOWN
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Sequence

UTC = timezone.utc

# ── Schema version ────────────────────────────────────────────────────────────

SCHEMA_VERSION = "AQL-SCANNER-V1"

# ── Availability classes ───────────────────────────────────────────────────────

AVAILABILITY_LIVE_PIT = "LIVE_PIT"
AVAILABILITY_RETRO = "RETROSPECTIVE_NON_PIT"
AVAILABILITY_UNKNOWN = "UNKNOWN"
AVAILABILITY_CLASSES = frozenset({AVAILABILITY_LIVE_PIT, AVAILABILITY_RETRO, AVAILABILITY_UNKNOWN})

# ── Candidate lifecycle ────────────────────────────────────────────────────────

STAGE_DISCOVERED = "DISCOVERED"
STAGE_SCREENED = "SCREENED"
STAGE_QUALIFIED = "QUALIFIED"
STAGE_NOMINATED = "NOMINATED"
STAGE_REJECTED = "REJECTED"
STAGE_EXPIRED = "EXPIRED"
STAGE_UNKNOWN = "UNKNOWN"
TERMINAL_STAGES = frozenset({STAGE_REJECTED, STAGE_EXPIRED, STAGE_UNKNOWN})


# ── Primitive helpers ──────────────────────────────────────────────────────────

def _utc(value: datetime) -> datetime:
    if not isinstance(value, datetime):
        raise ValueError("TIMESTAMP_MUST_BE_DATETIME")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("TIMESTAMP_MUST_BE_TZ_AWARE")
    return value.astimezone(UTC)


def _decimal(value: object) -> Decimal:
    if isinstance(value, bool):
        raise ValueError("BOOL_NOT_NUMERIC")
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ValueError("INVALID_NUMERIC_VALUE") from exc
    if not result.is_finite():
        raise ValueError("NON_FINITE_NUMERIC_VALUE")
    return result


def canonical_bytes(obj: object) -> bytes:
    """Deterministic UTF-8 JSON bytes — sorted keys, no extra whitespace."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, default=str).encode("utf-8")


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


# ── G1: Immutable bar admission ────────────────────────────────────────────────

@dataclass(frozen=True)
class AdmittedBar:
    """A single OHLCV bar that has passed PIT admission for a given cutoff.

    source_id    — opaque dataset/source identity string (e.g. dataset SHA or name)
    timeframe    — "5m" | "30m" | "1h" | "4h" | "1d" | "1w"
    symbol       — e.g. "BTCUSDT"
    open_at      — bar open time (UTC, inclusive)
    close_at     — bar close time (UTC, exclusive boundary)
    available_at — earliest time this bar was known to the system (receipt proxy)
    """
    source_id: str
    timeframe: str
    symbol: str
    open_at: datetime
    close_at: datetime
    available_at: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    base_volume: Decimal
    quote_volume: Decimal

    def __post_init__(self) -> None:
        for f in ("open_at", "close_at", "available_at"):
            object.__setattr__(self, f, _utc(getattr(self, f)))
        for f in ("open", "high", "low", "close", "base_volume", "quote_volume"):
            object.__setattr__(self, f, _decimal(getattr(self, f)))
        if not self.source_id or not isinstance(self.source_id, str):
            raise ValueError("SOURCE_ID_REQUIRED")
        if not self.symbol or not isinstance(self.symbol, str):
            raise ValueError("SYMBOL_REQUIRED")
        if self.timeframe not in {"5m", "30m", "1h", "4h", "1d", "1w"}:
            raise ValueError(f"UNSUPPORTED_TIMEFRAME:{self.timeframe}")

    def validate_pit(self, cutoff_at: datetime) -> list[str]:
        """Return list of PIT violation codes; empty list means bar is PIT-clean."""
        cutoff_at = _utc(cutoff_at)
        errors: list[str] = []
        if self.close_at > cutoff_at:
            errors.append("BAR_NOT_CLOSED_AT_CUTOFF")
        if self.available_at > cutoff_at:
            errors.append("BAR_NOT_AVAILABLE_AT_CUTOFF")
        if self.close_at <= self.open_at:
            errors.append("BAR_INVALID_DURATION")
        if self.available_at < self.close_at:
            errors.append("BAR_AVAILABLE_BEFORE_CLOSE")
        if self.high < self.low or self.low <= 0:
            errors.append("BAR_INVALID_OHLC")
        if not (self.low <= self.open <= self.high and self.low <= self.close <= self.high):
            errors.append("BAR_OHLC_OUT_OF_RANGE")
        if self.base_volume < 0 or self.quote_volume < 0:
            errors.append("BAR_NEGATIVE_VOLUME")
        return errors


@dataclass(frozen=True)
class AdmissionResult:
    """Result of admitting a sequence of bars for a single symbol/timeframe/cutoff."""
    symbol: str
    timeframe: str
    cutoff_at: datetime
    source_id: str
    availability_class: str
    admitted: tuple[AdmittedBar, ...]
    rejected_count: int
    admission_errors: tuple[str, ...]  # per-bar error codes (deduplicated)
    bars_requested: int
    bars_admitted: int

    @property
    def is_clean(self) -> bool:
        return not self.admission_errors and self.rejected_count == 0

    def as_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "cutoff_at": self.cutoff_at.isoformat(),
            "source_id": self.source_id,
            "availability_class": self.availability_class,
            "bars_requested": self.bars_requested,
            "bars_admitted": self.bars_admitted,
            "rejected_count": self.rejected_count,
            "admission_errors": list(self.admission_errors),
            "is_clean": self.is_clean,
        }


def admit_bars(
    bars: Sequence[AdmittedBar],
    cutoff_at: datetime,
    *,
    source_id: str,
    availability_class: str,
) -> AdmissionResult:
    """Admit bars for PIT-safe feature computation.

    Bars failing PIT validation are rejected silently (counted + error codes kept).
    The returned AdmissionResult carries only bars that passed.
    """
    if availability_class not in AVAILABILITY_CLASSES:
        raise ValueError(f"UNKNOWN_AVAILABILITY_CLASS:{availability_class}")
    cutoff_at = _utc(cutoff_at)
    admitted: list[AdmittedBar] = []
    rejected = 0
    all_errors: list[str] = []
    for bar in bars:
        errs = bar.validate_pit(cutoff_at)
        if errs:
            rejected += 1
            all_errors.extend(errs)
        else:
            admitted.append(bar)
    # Sort admitted bars by open_at ascending (stable, deterministic)
    admitted.sort(key=lambda b: b.open_at)
    symbol = bars[0].symbol if bars else ""
    timeframe = bars[0].timeframe if bars else ""
    return AdmissionResult(
        symbol=symbol,
        timeframe=timeframe,
        cutoff_at=cutoff_at,
        source_id=source_id,
        availability_class=availability_class,
        admitted=tuple(admitted),
        rejected_count=rejected,
        admission_errors=tuple(dict.fromkeys(all_errors)),
        bars_requested=len(bars),
        bars_admitted=len(admitted),
    )


# ── G1: Source manifest ────────────────────────────────────────────────────────

@dataclass(frozen=True)
class SourceManifest:
    """Immutable dataset identity frozen before any feature is computed.

    dataset_id    — opaque identifier for the historical dataset used
    dataset_sha   — SHA-256 of the dataset content (or provenance hash)
    schema_version — scanner schema version string
    cutoff_at     — decision cutoff frozen in this manifest
    created_at    — when this manifest was created (wall clock)
    """
    dataset_id: str
    dataset_sha: str
    schema_version: str
    cutoff_at: datetime
    created_at: datetime

    def __post_init__(self) -> None:
        for f in ("cutoff_at", "created_at"):
            object.__setattr__(self, f, _utc(getattr(self, f)))

    def as_dict(self) -> dict:
        return {
            "dataset_id": self.dataset_id,
            "dataset_sha": self.dataset_sha,
            "schema_version": self.schema_version,
            "cutoff_at": self.cutoff_at.isoformat(),
            "created_at": self.created_at.isoformat(),
        }

    @property
    def manifest_sha(self) -> str:
        return sha256_hex(canonical_bytes(self.as_dict()))


# ── G6: ScannerNominationEnvelope — typed output contract ──────────────────────

@dataclass
class ScannerNominationEnvelope:
    """ATLAS scanner output contract.

    Immutable once sealed.  Digest is SHA-256 of canonical JSON bytes of as_dict().
    Never a production signal, trade command, or delivery authorization.
    """
    scanner_id: str          # identifies this scanner instance / run
    candidate_id: str        # symbol + cutoff identity
    profile_id: str          # scoring profile used (e.g. "INTRADAY", "SWING")
    market: str              # e.g. "BINANCE:SPOT:USDT"
    cutoff_at: datetime      # decision cutoff — no feature may use data after this
    availability_class: str  # LIVE_PIT | RETROSPECTIVE_NON_PIT | UNKNOWN
    stage: str               # DISCOVERED | SCREENED | QUALIFIED | NOMINATED | REJECTED | ...
    source_manifest: dict    # SourceManifest.as_dict()
    feature_snapshot: dict   # MTF features at cutoff (names → str values or None)
    reasons: list[str]       # human/machine-readable reason codes
    coverage: dict           # missingness, completeness flags
    score: str | None = None # research strength score (str Decimal) or None
    score_status: str = "SCORE_UNAVAILABLE"
    publishable: bool = False
    delivery_authorized: bool = False
    _digest: str | None = field(default=None, repr=False, compare=False)

    def seal(self) -> "ScannerNominationEnvelope":
        """Freeze digest.  Call once all fields are populated."""
        d = self.as_dict(include_digest=False)
        object.__setattr__(self, "_digest", sha256_hex(canonical_bytes(d)))
        return self

    @property
    def digest(self) -> str | None:
        return self._digest

    def as_dict(self, *, include_digest: bool = True) -> dict:
        base: dict[str, Any] = {
            "schema_version": SCHEMA_VERSION,
            "scanner_id": self.scanner_id,
            "candidate_id": self.candidate_id,
            "profile_id": self.profile_id,
            "market": self.market,
            "cutoff_at": self.cutoff_at.isoformat() if isinstance(self.cutoff_at, datetime) else self.cutoff_at,
            "availability_class": self.availability_class,
            "stage": self.stage,
            "source_manifest": self.source_manifest,
            "feature_snapshot": self.feature_snapshot,
            "reasons": sorted(set(self.reasons)),
            "coverage": self.coverage,
            "score": self.score,
            "score_status": self.score_status,
            "publishable": False,          # always False at research stage
            "delivery_authorized": False,  # always False at research stage
        }
        if include_digest:
            base["digest"] = self._digest
        return base

    def to_json(self) -> str:
        return json.dumps(self.as_dict(), sort_keys=True, separators=(",", ":"),
                          ensure_ascii=False, default=str)
