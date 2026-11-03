"""G7 — Offline multi-symbol, multi-timeframe, multi-profile scanner engine.

Orchestrates: universe snapshot → bar admission → feature computation →
              screening → evidence receipt → envelope sealing.

Design constraints:
  - No network calls. All data supplied by the caller.
  - Deterministic: identical inputs → byte-identical outputs.
  - Fail-closed: any missing essential bar data → SCORE_UNAVAILABLE (not omitted).
  - All outputs RETROSPECTIVE_NON_PIT for P0 offline development.
  - publishable and delivery_authorized are always False.

ScanRun: one complete engine pass over a universe snapshot.
  run_id   — SHA-256 of canonical run config + cutoff_at
  receipts — EvidenceReceipt for every (symbol, profile) pair attempted
  envelopes — only NOMINATED results (by default), or all if include_all=True
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from typing import Sequence

from .contracts import (
    AdmittedBar, SourceManifest, ScannerNominationEnvelope,
    AVAILABILITY_RETRO, STAGE_NOMINATED, _utc, canonical_bytes, sha256_hex,
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

    def run_id_seed(self, cutoff_at: datetime) -> str:
        return sha256_hex(canonical_bytes({
            "scanner_id": self.scanner_id,
            "profiles": list(self.profiles),
            "candidate_limit": self.candidate_limit,
            "candidate_offset": self.candidate_offset,
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
        }


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
          Bars must already be PIT-admitted (close_at ≤ cutoff_at).
          Caller may pass an empty dict for symbols to produce SCORE_UNAVAILABLE results.

        cutoff_at: if None, uses universe.cutoff_at.
        include_all_envelopes: if True, include all produced envelopes (not only NOMINATED).
        """
        if cutoff_at is None:
            cutoff_at = universe.cutoff_at
        cutoff_at = _utc(cutoff_at)

        config = self._config
        run_id = config.run_id_seed(cutoff_at)
        spool = BoundedSpool(capacity=config.spool_capacity, spool_id=run_id)
        errors: list[str] = []

        # Select candidates
        selected: tuple[UniverseItem, ...] = select_candidates(
            universe, config.candidate_limit, config.candidate_offset)
        symbols_attempted = [item.symbol for item in selected]

        all_envelopes: list[ScannerNominationEnvelope] = []
        nominated_envelopes: list[ScannerNominationEnvelope] = []

        for item in selected:
            symbol = item.symbol
            symbol_bars = bars_by_symbol_tf.get(symbol, {})

            # Bid/ask from market info
            bid = item.market.bid if item.market else None
            ask = item.market.ask if item.market else None

            # Compute MTF features
            try:
                feature_snapshot = compute_features(
                    symbol=symbol,
                    cutoff_at=cutoff_at,
                    bars_by_tf=symbol_bars,
                    bid=bid,
                    ask=ask,
                )
            except Exception as exc:
                errors.append(f"FEATURE_ERROR:{symbol}:{exc}")
                continue

            # Screen across all configured profiles
            try:
                candidates = screen_all_profiles(feature_snapshot, list(config.profiles))
            except Exception as exc:
                errors.append(f"SCREENING_ERROR:{symbol}:{exc}")
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
                    receipt = commit_receipt(
                        scanner_id=config.scanner_id,
                        symbol=symbol,
                        profile=profile,
                        stage=candidate.stage,
                        score=str(candidate.score) if candidate.score is not None else None,
                        score_status=candidate.score_status,
                        payload=envelope.as_dict(),
                        claim_at=cutoff_at,
                        committed_at=datetime.now(UTC),
                    )
                    spool.append(receipt)
                    if include_all_envelopes:
                        all_envelopes.append(envelope)
                    if candidate.stage == STAGE_NOMINATED:
                        nominated_envelopes.append(envelope)
                except Exception as exc:
                    errors.append(f"ENVELOPE_ERROR:{symbol}:{profile}:{exc}")

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
        )
