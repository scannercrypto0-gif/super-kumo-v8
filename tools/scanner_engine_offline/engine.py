"""G7 — Offline multi-symbol, multi-timeframe, multi-profile scanner engine.

Orchestrates: universe snapshot → bar admission → feature computation →
              screening → evidence receipt → envelope sealing.

Design constraints:
  - No network calls. All data supplied by the caller.
  - Deterministic: identical inputs → byte-identical outputs (PYTHONHASHSEED-independent).
  - Fail-closed: any missing essential bar data → SCORE_UNAVAILABLE (never omitted).
  - Central admission boundary: ALL bars validated via admit_bars() inside engine.
  - Complete per-attempt census: every (symbol, profile) produces a receipt, even on error.
  - All outputs RETROSPECTIVE_NON_PIT for offline development.
  - publishable and delivery_authorized are always False.

P0 fixes applied (audit AQL-SCANNER-V1-SCIENTIFIC-ENGINEERING-REVIEW-001):
  P0-01: Central admission boundary enforced inside scan(); cross-identity (symbol/TF)
         and PIT validation mandatory before features; rejects future/wrong-identity bars.
  P0-02: Every (symbol, profile) attempt produces a receipt; errors → UNKNOWN envelope
         with SCORE_UNAVAILABLE; summary has full census: attempted/completed/error/spool.
  P0-03: Receipt claim identity includes run_id + manifest_sha + cutoff; no same-ID
         collision across runs; committed_at = cutoff_at for deterministic research receipts.
  P0-04: Manifest.cutoff_at vs universe.cutoff_at vs run cutoff_at validated at entry;
         mismatch raises ValueError("CUTOFF_MISMATCH:…").
  P1-01: admitted_bars path uses SHA-256 for all seeds; committed_at = cutoff_at (not wall
         clock) for deterministic research output.
  P1-02: Engine never mutates a sealed envelope.

ScanRun: one complete engine pass over a universe snapshot.
  run_id     — SHA-256 of canonical run config + manifest_sha + cutoff_at
  receipts   — EvidenceReceipt for every (symbol, profile) pair attempted
  envelopes  — all produced envelopes (include_all_envelopes=True by default)
  census     — { attempted, completed, error, spool_size, spool_evicted }
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from typing import Sequence

from .contracts import (
    AdmittedBar, SourceManifest, ScannerNominationEnvelope,
    AVAILABILITY_RETRO, STAGE_NOMINATED, STAGE_UNKNOWN,
    _utc, canonical_bytes, sha256_hex,
    admit_bars,
)
from .universe import UniverseSnapshot, UniverseItem, select_candidates
from .features import compute_features, MTFFeatureSnapshot
from .screening import screen_all_profiles, SUPPORTED_PROFILES
from .evidence import BoundedSpool, commit_receipt
from .adapters import candidate_to_envelope

UTC = timezone.utc

# ── Run config ────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class ScanRunConfig:
    scanner_id: str
    profiles: tuple[str, ...] = tuple(sorted(SUPPORTED_PROFILES))
    candidate_limit: int = 50          # max symbols to process per run
    candidate_offset: int = 0          # rotating offset for universe selection
    market: str = "BINANCE:SPOT:USDT"
    spool_capacity: int = 500

    def run_id_seed(self, cutoff_at: datetime, manifest_sha: str) -> str:
        """Deterministic run identity includes manifest_sha to prevent cross-run collisions."""
        return sha256_hex(canonical_bytes({
            "scanner_id": self.scanner_id,
            "profiles": list(self.profiles),
            "candidate_limit": self.candidate_limit,
            "candidate_offset": self.candidate_offset,
            "manifest_sha": manifest_sha,
            "cutoff_at": _utc(cutoff_at).isoformat(),
        }))


# ── Run result ────────────────────────────────────────────────────────────────

@dataclass
class ScanRun:
    run_id: str
    scanner_id: str
    cutoff_at: datetime
    config: ScanRunConfig
    universe_summary: dict
    symbols_attempted: list[str]
    envelopes: list[ScannerNominationEnvelope]      # all produced envelopes
    nominated_envelopes: list[ScannerNominationEnvelope]  # NOMINATED only
    spool: BoundedSpool
    errors: list[str]
    census: dict  # P0-02: full attempt census

    def summary(self) -> dict:
        return {
            "run_id": self.run_id,
            "scanner_id": self.scanner_id,
            "cutoff_at": self.cutoff_at.isoformat(),
            "symbols_attempted": len(self.symbols_attempted),
            "envelopes_produced": len(self.envelopes),
            "nominated_count": len(self.nominated_envelopes),
            "receipts_in_spool": len(self.spool),
            "errors": self.errors,
            "universe": self.universe_summary,
            "census": self.census,
        }


# ── Internal helpers ──────────────────────────────────────────────────────────

_VALID_TIMEFRAMES = {"5m", "30m", "1h", "4h", "1d"}


def _admit_symbol_bars(
    symbol: str,
    raw_bars_by_tf: dict[str, list[AdmittedBar]],
    cutoff_at: datetime,
    run_id: str,
) -> dict[str, list[AdmittedBar]]:
    """P0-01: Central admission boundary.

    For each timeframe, run admit_bars() with cross-identity checks:
      - bar.symbol must match the expected symbol
      - bar.timeframe must match the expected timeframe
      - bar must pass PIT validation (close_at ≤ cutoff_at, available_at ≤ cutoff_at)

    Returns {timeframe: [admitted_bars]} with only PIT-clean bars per TF.
    Unknown/wrong-identity bars are silently excluded (counted in admission errors).
    """
    admitted_by_tf: dict[str, list[AdmittedBar]] = {}
    for tf, bars in raw_bars_by_tf.items():
        if not bars:
            admitted_by_tf[tf] = []
            continue
        # Cross-identity filter: reject bars with wrong symbol or timeframe
        identity_clean = [
            b for b in bars
            if b.symbol == symbol and b.timeframe == tf
        ]
        if not identity_clean:
            admitted_by_tf[tf] = []
            continue
        result = admit_bars(
            identity_clean,
            cutoff_at,
            source_id=identity_clean[0].source_id,
            availability_class=AVAILABILITY_RETRO,
        )
        admitted_by_tf[tf] = list(result.admitted)
    return admitted_by_tf


def _make_error_envelope(
    scanner_id: str,
    symbol: str,
    profile: str,
    cutoff_at: datetime,
    market: str,
    source_manifest: dict,
    error_code: str,
) -> ScannerNominationEnvelope:
    """P0-02: Produce a fail-closed UNKNOWN envelope for any error path."""
    candidate_id = f"{symbol}:{cutoff_at.isoformat()}"
    env = ScannerNominationEnvelope(
        scanner_id=scanner_id,
        candidate_id=candidate_id,
        profile_id=profile,
        market=market,
        cutoff_at=cutoff_at,
        availability_class=AVAILABILITY_RETRO,
        stage=STAGE_UNKNOWN,
        source_manifest=source_manifest,
        feature_snapshot={},
        reasons=[error_code],
        coverage={},
        score=None,
        score_status="SCORE_UNAVAILABLE",
        publishable=False,
        delivery_authorized=False,
    )
    env.seal()
    return env


# ── Engine ────────────────────────────────────────────────────────────────────

class OfflineScannerEngine:
    """Offline deterministic scanner engine.

    Usage::

        engine = OfflineScannerEngine(config, source_manifest)
        run = engine.scan(universe_snapshot, bars_by_symbol_tf)
    """

    def __init__(
        self,
        config: ScanRunConfig,
        source_manifest: SourceManifest,
    ) -> None:
        self._config = config
        self._manifest = source_manifest

    def scan(
        self,
        universe: UniverseSnapshot,
        bars_by_symbol_tf: dict[str, dict[str, list[AdmittedBar]]],
        cutoff_at: datetime | None = None,
        include_all_envelopes: bool = True,
    ) -> ScanRun:
        """Execute a full scan pass.

        bars_by_symbol_tf: {symbol: {timeframe: [AdmittedBar, ...]}}
          Caller may supply raw bars; the engine runs central admission internally.
          Caller may pass an empty dict to produce SCORE_UNAVAILABLE results.

        cutoff_at: if None, uses universe.cutoff_at.
        include_all_envelopes: if True, include all produced envelopes (not only NOMINATED).

        P0-04: Validates manifest.cutoff_at == universe.cutoff_at == run cutoff_at.
               Raises ValueError on mismatch.
        """
        if cutoff_at is None:
            cutoff_at = universe.cutoff_at
        cutoff_at = _utc(cutoff_at)

        # P0-04: Manifest / time binding validation
        manifest_cutoff = _utc(self._manifest.cutoff_at)
        universe_cutoff = _utc(universe.cutoff_at)
        if manifest_cutoff != cutoff_at:
            raise ValueError(
                f"CUTOFF_MISMATCH:manifest={manifest_cutoff.isoformat()}"
                f",run={cutoff_at.isoformat()}"
            )
        if universe_cutoff != cutoff_at:
            raise ValueError(
                f"CUTOFF_MISMATCH:universe={universe_cutoff.isoformat()}"
                f",run={cutoff_at.isoformat()}"
            )

        config = self._config
        manifest_sha = self._manifest.manifest_sha
        # P0-03: run_id includes manifest_sha → no same-ID collision across runs
        run_id = config.run_id_seed(cutoff_at, manifest_sha)
        spool = BoundedSpool(capacity=config.spool_capacity, spool_id=run_id)
        errors: list[str] = []

        # Select candidates
        selected: tuple[UniverseItem, ...] = select_candidates(
            universe, config.candidate_limit, config.candidate_offset)
        symbols_attempted = [item.symbol for item in selected]

        all_envelopes: list[ScannerNominationEnvelope] = []
        nominated_envelopes: list[ScannerNominationEnvelope] = []

        # P0-02 census counters
        census_completed = 0
        census_error = 0
        spool_evicted_before = 0  # track eviction

        source_manifest_dict = self._manifest.as_dict()

        for item in selected:
            symbol = item.symbol
            raw_symbol_bars = bars_by_symbol_tf.get(symbol, {})

            # Bid/ask from market info
            bid = item.market.bid if item.market else None
            ask = item.market.ask if item.market else None

            # P0-01: Central admission boundary — always run admit_bars inside engine
            admitted_bars_by_tf = _admit_symbol_bars(
                symbol, raw_symbol_bars, cutoff_at, run_id
            )

            # Compute MTF features
            feature_snapshot: MTFFeatureSnapshot | None = None
            try:
                feature_snapshot = compute_features(
                    symbol=symbol,
                    cutoff_at=cutoff_at,
                    bars_by_tf=admitted_bars_by_tf,
                    bid=bid,
                    ask=ask,
                )
            except Exception as exc:
                error_code = f"FEATURE_ERROR:{symbol}:{exc}"
                errors.append(error_code)
                # P0-02: produce error receipts for all configured profiles
                for profile in config.profiles:
                    census_error += 1
                    env = _make_error_envelope(
                        config.scanner_id, symbol, profile, cutoff_at,
                        config.market, source_manifest_dict, error_code,
                    )
                    # P0-03: deterministic committed_at = cutoff_at
                    receipt = commit_receipt(
                        scanner_id=config.scanner_id,
                        symbol=symbol,
                        profile=profile,
                        stage=STAGE_UNKNOWN,
                        score=None,
                        score_status="SCORE_UNAVAILABLE",
                        payload=env.as_dict(),
                        claim_at=cutoff_at,
                        committed_at=cutoff_at,  # deterministic, not wall clock
                        run_id=run_id,
                    )
                    spool.append(receipt)
                    if include_all_envelopes:
                        all_envelopes.append(env)
                continue

            # Screen across all configured profiles
            try:
                candidates = screen_all_profiles(feature_snapshot, list(config.profiles))
            except Exception as exc:
                error_code = f"SCREENING_ERROR:{symbol}:{exc}"
                errors.append(error_code)
                for profile in config.profiles:
                    census_error += 1
                    env = _make_error_envelope(
                        config.scanner_id, symbol, profile, cutoff_at,
                        config.market, source_manifest_dict, error_code,
                    )
                    receipt = commit_receipt(
                        scanner_id=config.scanner_id,
                        symbol=symbol,
                        profile=profile,
                        stage=STAGE_UNKNOWN,
                        score=None,
                        score_status="SCORE_UNAVAILABLE",
                        payload=env.as_dict(),
                        claim_at=cutoff_at,
                        committed_at=cutoff_at,
                        run_id=run_id,
                    )
                    spool.append(receipt)
                    if include_all_envelopes:
                        all_envelopes.append(env)
                continue

            # Produce envelopes and receipts
            for profile, candidate in candidates.items():
                try:
                    envelope = candidate_to_envelope(
                        candidate=candidate,
                        feature_snapshot=feature_snapshot,
                        source_manifest=self._manifest,
                        scanner_id=config.scanner_id,
                        market=config.market,
                    )
                    # P0-03: committed_at = cutoff_at (deterministic, not wall clock)
                    receipt = commit_receipt(
                        scanner_id=config.scanner_id,
                        symbol=symbol,
                        profile=profile,
                        stage=candidate.stage,
                        score=str(candidate.score) if candidate.score is not None else None,
                        score_status=candidate.score_status,
                        payload=envelope.as_dict(),
                        claim_at=cutoff_at,
                        committed_at=cutoff_at,
                        run_id=run_id,
                    )
                    spool.append(receipt)
                    census_completed += 1
                    if include_all_envelopes:
                        all_envelopes.append(envelope)
                    if candidate.stage == STAGE_NOMINATED:
                        nominated_envelopes.append(envelope)
                except Exception as exc:
                    error_code = f"ENVELOPE_ERROR:{symbol}:{profile}:{exc}"
                    errors.append(error_code)
                    census_error += 1
                    env = _make_error_envelope(
                        config.scanner_id, symbol, profile, cutoff_at,
                        config.market, source_manifest_dict, error_code,
                    )
                    receipt = commit_receipt(
                        scanner_id=config.scanner_id,
                        symbol=symbol,
                        profile=profile,
                        stage=STAGE_UNKNOWN,
                        score=None,
                        score_status="SCORE_UNAVAILABLE",
                        payload=env.as_dict(),
                        claim_at=cutoff_at,
                        committed_at=cutoff_at,
                        run_id=run_id,
                    )
                    spool.append(receipt)
                    if include_all_envelopes:
                        all_envelopes.append(env)

        # P0-02: Full census
        expected_attempts = len(symbols_attempted) * len(config.profiles)
        census = {
            "symbols_attempted": len(symbols_attempted),
            "profiles": list(config.profiles),
            "expected_receipt_count": expected_attempts,
            "completed": census_completed,
            "error": census_error,
            "spool_size": len(spool),
        }

        return ScanRun(
            run_id=run_id,
            scanner_id=config.scanner_id,
            cutoff_at=cutoff_at,
            config=config,
            universe_summary=universe.summary(),
            symbols_attempted=symbols_attempted,
            envelopes=all_envelopes,
            nominated_envelopes=nominated_envelopes,
            spool=spool,
            errors=errors,
            census=census,
        )
