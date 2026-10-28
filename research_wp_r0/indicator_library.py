"""
SF-IND-01 — Unified Research Indicator Library V1
==================================================
Deterministic, point-in-time (PIT) correct, immutable versioned indicator
computation library for AQL-CRYPTO-RESEARCH-001 Strategy Factory lane.

Design guarantees
-----------------
* PIT correctness — all bar retrievals go through CustodyAccessor with an
  explicit ``decision_cutoff_ms``; no bar with ``observation_cutoff_ms >
  decision_cutoff_ms`` can enter computation.
* Warmup policy — each indicator declares ``min_warmup_bars``; leading bars
  are consumed silently; ``warmup_bars_consumed`` is recorded on every result.
* Fail-closed gap policy — ``CustodyAccessor.range_query(require_complete=True)``
  by default; missing intervals raise rather than silently producing partial
  results.  Partial mode is an explicit opt-in.
* Immutable results — ``IndicatorResult`` and ``IndicatorManifest`` are frozen
  dataclasses; SHA-256 provenance hash covers all fields including the source
  dataset version and manifest hash.
* Roundtrip validation — ``from_dict()`` rejects tampered provenance hashes.
* Stdlib-only runtime — no external dependencies in library code.

No live exchange calls, no credentials, no G1 pipeline coupling.
Research / Strategy Factory lane only.

Issue: #59 (SF-IND-01)
Depends on: SF-DATA-01 (PR #57, commit cf4339e83d8ce2fe30cc727b6c470f1fb0bf63bb)
"""
from __future__ import annotations

import math
import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

# SF-DATA-01 public surface (same package, no src/aql coupling)
from research_wp_r0.historical_library import (
    CustodyAccessor,
    HistoricalBar,
)

__all__ = [
    "IndicatorResult",
    "IndicatorManifest",
    "IndicatorLibrary",
    "SMAIndicator",
    "EMAIndicator",
    "RSIIndicator",
    "RSIIndicatorV2",
    "ATRIndicator",
]

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _sha256_hex(*parts: Any) -> str:
    h = hashlib.sha256()
    for p in parts:
        h.update(json.dumps(p, sort_keys=True, separators=(",", ":")).encode())
    return h.hexdigest()


def _freeze_params(kwargs: Dict[str, Any]) -> Tuple[Tuple[str, Any], ...]:
    return tuple(sorted(kwargs.items()))


# ---------------------------------------------------------------------------
# IndicatorResult
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class IndicatorResult:
    """
    Immutable result for one bar from one indicator computation.

    Parameters recorded per-result enable full audit trail:
    which dataset/version/manifest, which PIT cutoff, which indicator
    parameters, how many warmup bars were consumed.
    """

    indicator_id: str
    version: str
    dataset_id: str
    dataset_version: int
    dataset_manifest_hash: str
    bar_open_ms: int
    decision_cutoff_ms: int
    value: Optional[float]
    parameters: Tuple[Tuple[str, Any], ...]
    warmup_bars_consumed: int
    partial_coverage: bool
    provenance_hash: str

    @staticmethod
    def _hash_fields(
        indicator_id: str,
        version: str,
        dataset_id: str,
        dataset_version: int,
        dataset_manifest_hash: str,
        bar_open_ms: int,
        decision_cutoff_ms: int,
        value: Optional[float],
        parameters: Tuple[Tuple[str, Any], ...],
        warmup_bars_consumed: int,
        partial_coverage: bool,
    ) -> str:
        return _sha256_hex(
            indicator_id, version,
            dataset_id, dataset_version, dataset_manifest_hash,
            bar_open_ms, decision_cutoff_ms,
            value, list(parameters),
            warmup_bars_consumed, partial_coverage,
        )

    @classmethod
    def create(
        cls,
        indicator_id: str,
        version: str,
        dataset_id: str,
        dataset_version: int,
        dataset_manifest_hash: str,
        bar_open_ms: int,
        decision_cutoff_ms: int,
        value: Optional[float],
        parameters: Tuple[Tuple[str, Any], ...],
        warmup_bars_consumed: int,
        partial_coverage: bool,
    ) -> "IndicatorResult":
        ph = cls._hash_fields(
            indicator_id, version,
            dataset_id, dataset_version, dataset_manifest_hash,
            bar_open_ms, decision_cutoff_ms,
            value, parameters,
            warmup_bars_consumed, partial_coverage,
        )
        return cls(
            indicator_id=indicator_id,
            version=version,
            dataset_id=dataset_id,
            dataset_version=dataset_version,
            dataset_manifest_hash=dataset_manifest_hash,
            bar_open_ms=bar_open_ms,
            decision_cutoff_ms=decision_cutoff_ms,
            value=value,
            parameters=parameters,
            warmup_bars_consumed=warmup_bars_consumed,
            partial_coverage=partial_coverage,
            provenance_hash=ph,
        )

    def verify_integrity(self) -> bool:
        expected = self._hash_fields(
            self.indicator_id, self.version,
            self.dataset_id, self.dataset_version, self.dataset_manifest_hash,
            self.bar_open_ms, self.decision_cutoff_ms,
            self.value, self.parameters,
            self.warmup_bars_consumed, self.partial_coverage,
        )
        return self.provenance_hash == expected

    def to_dict(self) -> Dict[str, Any]:
        return {
            "indicator_id": self.indicator_id,
            "version": self.version,
            "dataset_id": self.dataset_id,
            "dataset_version": self.dataset_version,
            "dataset_manifest_hash": self.dataset_manifest_hash,
            "bar_open_ms": self.bar_open_ms,
            "decision_cutoff_ms": self.decision_cutoff_ms,
            "value": self.value,
            "parameters": list(self.parameters),
            "warmup_bars_consumed": self.warmup_bars_consumed,
            "partial_coverage": self.partial_coverage,
            "provenance_hash": self.provenance_hash,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "IndicatorResult":
        params: Tuple[Tuple[str, Any], ...] = tuple(
            (k, v) for k, v in d["parameters"]
        )
        stored = d["provenance_hash"]
        expected = cls._hash_fields(
            d["indicator_id"], d["version"],
            d["dataset_id"], d["dataset_version"], d["dataset_manifest_hash"],
            d["bar_open_ms"], d["decision_cutoff_ms"],
            d["value"], params,
            d["warmup_bars_consumed"], d["partial_coverage"],
        )
        if stored != expected:
            raise ValueError(
                f"IndicatorResult provenance_hash mismatch: "
                f"stored {stored!r} != computed {expected!r}"
            )
        return cls(
            indicator_id=d["indicator_id"],
            version=d["version"],
            dataset_id=d["dataset_id"],
            dataset_version=d["dataset_version"],
            dataset_manifest_hash=d["dataset_manifest_hash"],
            bar_open_ms=d["bar_open_ms"],
            decision_cutoff_ms=d["decision_cutoff_ms"],
            value=d["value"],
            parameters=params,
            warmup_bars_consumed=d["warmup_bars_consumed"],
            partial_coverage=d["partial_coverage"],
            provenance_hash=stored,
        )


# ---------------------------------------------------------------------------
# IndicatorManifest
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class IndicatorManifest:
    """
    Immutable summary of a complete indicator computation run.

    ``computation_hash`` is SHA-256 of all result ``provenance_hash`` values
    in ascending ``bar_open_ms`` order — one-stop tamper detection.
    """

    indicator_id: str
    dataset_id: str
    dataset_version: int
    dataset_manifest_hash: str
    decision_cutoff_ms: int
    parameter_set: Tuple[Tuple[str, Any], ...]
    warmup_policy: int
    result_count: int
    computation_hash: str

    @staticmethod
    def _hash_results(results: Sequence[IndicatorResult]) -> str:
        return _sha256_hex([r.provenance_hash for r in results])

    @classmethod
    def create(
        cls,
        indicator_id: str,
        dataset_id: str,
        dataset_version: int,
        dataset_manifest_hash: str,
        decision_cutoff_ms: int,
        parameter_set: Tuple[Tuple[str, Any], ...],
        warmup_policy: int,
        results: Sequence[IndicatorResult],
    ) -> "IndicatorManifest":
        return cls(
            indicator_id=indicator_id,
            dataset_id=dataset_id,
            dataset_version=dataset_version,
            dataset_manifest_hash=dataset_manifest_hash,
            decision_cutoff_ms=decision_cutoff_ms,
            parameter_set=parameter_set,
            warmup_policy=warmup_policy,
            result_count=len(results),
            computation_hash=cls._hash_results(results),
        )

    def verify(self, results: Sequence[IndicatorResult]) -> bool:
        return (
            len(results) == self.result_count
            and self.computation_hash == self._hash_results(results)
            and all(
                isinstance(item, IndicatorResult)
                and item.verify_integrity()
                and item.indicator_id == self.indicator_id
                and item.dataset_id == self.dataset_id
                and item.dataset_version == self.dataset_version
                and item.dataset_manifest_hash == self.dataset_manifest_hash
                and item.decision_cutoff_ms == self.decision_cutoff_ms
                and item.parameters == self.parameter_set
                and item.warmup_bars_consumed == self.warmup_policy
                for item in results
            )
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "indicator_id": self.indicator_id,
            "dataset_id": self.dataset_id,
            "dataset_version": self.dataset_version,
            "dataset_manifest_hash": self.dataset_manifest_hash,
            "decision_cutoff_ms": self.decision_cutoff_ms,
            "parameter_set": list(self.parameter_set),
            "warmup_policy": self.warmup_policy,
            "result_count": self.result_count,
            "computation_hash": self.computation_hash,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "IndicatorManifest":
        return cls(
            indicator_id=d["indicator_id"],
            dataset_id=d["dataset_id"],
            dataset_version=d["dataset_version"],
            dataset_manifest_hash=d["dataset_manifest_hash"],
            decision_cutoff_ms=d["decision_cutoff_ms"],
            parameter_set=tuple((k, v) for k, v in d["parameter_set"]),
            warmup_policy=d["warmup_policy"],
            result_count=d["result_count"],
            computation_hash=d["computation_hash"],
        )


# ---------------------------------------------------------------------------
# Internal helpers: extract dataset metadata from CustodyAccessor
# ---------------------------------------------------------------------------

def _get_ds_meta(
    accessor: CustodyAccessor, dataset_id: str, version: Optional[int]
) -> Tuple[int, str]:
    """Return (dataset_version, manifest_integrity_hash) for the dataset."""
    lib = accessor._library  # type: ignore[attr-defined]
    if dataset_id not in lib._datasets:
        raise KeyError(f"Dataset {dataset_id!r} not found in library")
    ds_versions = lib._datasets[dataset_id]
    v = version if version is not None else max(ds_versions)
    if v not in ds_versions:
        raise KeyError(f"Dataset {dataset_id!r} version {v} not found")
    manifest = ds_versions[v][1]
    return v, (manifest.manifest_integrity_hash or "")


# ---------------------------------------------------------------------------
# Base indicator
# ---------------------------------------------------------------------------

class _BaseIndicator:
    """Abstract base class. Subclasses implement ``_compute_values``."""

    indicator_id: str = "BASE_v1"
    version: str = "1"
    min_warmup_bars: int = 0

    def __init__(self, **kwargs: Any) -> None:
        self._params: Tuple[Tuple[str, Any], ...] = _freeze_params(kwargs)
        self._validate_params()

    def _validate_params(self) -> None:
        pass  # override to raise ValueError on bad params

    @property
    def params(self) -> Dict[str, Any]:
        return dict(self._params)

    def compute(
        self,
        accessor: CustodyAccessor,
        dataset_id: str,
        start_ms: int,
        end_ms: int,
        decision_cutoff_ms: int,
        *,
        version: Optional[int] = None,
        require_complete: bool = True,
    ) -> Tuple[List[IndicatorResult], IndicatorManifest]:
        """
        Compute indicator over bars in [start_ms, end_ms].

        Parameters
        ----------
        accessor : CustodyAccessor
            Must be bound to a HistoricalLibrary containing ``dataset_id``.
        dataset_id : str
            Source dataset identifier.
        start_ms, end_ms : int
            Bar open time range (inclusive).
        decision_cutoff_ms : int
            PIT cutoff — bars not yet observable at this time are excluded.
        version : int, optional
            Dataset version (latest if None).
        require_complete : bool
            Passed through to ``CustodyAccessor.range_query``; True (default)
            raises on gaps.

        Returns
        -------
        (results, manifest)
            ``results`` contains one entry per non-warmup bar.
        """
        ds_version, ds_manifest_hash = _get_ds_meta(accessor, dataset_id, version)

        bars: List[HistoricalBar] = accessor.range_query(
            dataset_id=dataset_id,
            start_ms=start_ms,
            end_ms=end_ms,
            decision_cutoff_ms=decision_cutoff_ms,
            version=ds_version,
            require_complete=require_complete,
        )

        closes = [b.close for b in bars]
        raw: List[Optional[float]] = self._compute_values(closes, bars)

        warmup = self.min_warmup_bars
        partial = not require_complete

        results: List[IndicatorResult] = []
        for i in range(warmup, len(bars)):
            results.append(
                IndicatorResult.create(
                    indicator_id=self.indicator_id,
                    version=self.version,
                    dataset_id=dataset_id,
                    dataset_version=ds_version,
                    dataset_manifest_hash=ds_manifest_hash,
                    bar_open_ms=bars[i].bar_open,
                    decision_cutoff_ms=decision_cutoff_ms,
                    value=raw[i],
                    parameters=self._params,
                    warmup_bars_consumed=warmup,
                    partial_coverage=partial,
                )
            )

        manifest = IndicatorManifest.create(
            indicator_id=self.indicator_id,
            dataset_id=dataset_id,
            dataset_version=ds_version,
            dataset_manifest_hash=ds_manifest_hash,
            decision_cutoff_ms=decision_cutoff_ms,
            parameter_set=self._params,
            warmup_policy=warmup,
            results=results,
        )
        return results, manifest

    def _compute_values(
        self, closes: List[float], bars: List[HistoricalBar]
    ) -> List[Optional[float]]:
        raise NotImplementedError


# ---------------------------------------------------------------------------
# SMA
# ---------------------------------------------------------------------------

class SMAIndicator(_BaseIndicator):
    """Simple Moving Average — period >= 2."""

    indicator_id = "SMA_v1"
    version = "1"

    def __init__(self, period: int) -> None:
        super().__init__(period=period)
        self.period = period
        self.min_warmup_bars = period - 1

    def _validate_params(self) -> None:
        p = dict(self._params).get("period", 0)
        if not isinstance(p, int) or p < 2:
            raise ValueError(f"SMA period must be int >= 2, got {p!r}")

    def _compute_values(
        self, closes: List[float], bars: List[HistoricalBar]
    ) -> List[Optional[float]]:
        n = len(closes)
        out: List[Optional[float]] = [None] * n
        p = self.period
        for i in range(p - 1, n):
            out[i] = sum(closes[i - p + 1 : i + 1]) / p
        return out


# ---------------------------------------------------------------------------
# EMA
# ---------------------------------------------------------------------------

class EMAIndicator(_BaseIndicator):
    """Exponential Moving Average. k = smoothing / (period + 1)."""

    indicator_id = "EMA_v1"
    version = "1"

    def __init__(self, period: int, smoothing: float = 2.0) -> None:
        super().__init__(period=period, smoothing=float(smoothing))
        self.period = period
        self.smoothing = float(smoothing)
        self.min_warmup_bars = period - 1

    def _validate_params(self) -> None:
        p = dict(self._params)
        if not isinstance(p.get("period"), int) or p["period"] < 2:
            raise ValueError(f"EMA period must be int >= 2, got {p.get('period')!r}")
        s = p.get("smoothing", 2.0)
        if type(s) not in (int, float) or not math.isfinite(s) or not 0 < s <= p["period"] + 1:
            raise ValueError(f"EMA smoothing must be > 0, got {s!r}")

    def _compute_values(
        self, closes: List[float], bars: List[HistoricalBar]
    ) -> List[Optional[float]]:
        n = len(closes)
        out: List[Optional[float]] = [None] * n
        p = self.period
        if n < p:
            return out
        k = self.smoothing / (p + 1)
        ema = sum(closes[:p]) / p
        out[p - 1] = ema
        for i in range(p, n):
            ema = closes[i] * k + ema * (1.0 - k)
            out[i] = ema
        return out


# ---------------------------------------------------------------------------
# RSI
# ---------------------------------------------------------------------------

class RSIIndicator(_BaseIndicator):
    """Relative Strength Index — Wilder's smoothing. period >= 2."""

    indicator_id = "RSI_v1"
    version = "1"

    def __init__(self, period: int = 14) -> None:
        super().__init__(period=period)
        self.period = period
        # First valid result at index `period` (needs period+1 bars total)
        self.min_warmup_bars = period

    def _validate_params(self) -> None:
        p = dict(self._params).get("period", 0)
        if not isinstance(p, int) or p < 2:
            raise ValueError(f"RSI period must be int >= 2, got {p!r}")

    @staticmethod
    def _rsi(avg_gain: float, avg_loss: float) -> float:
        if avg_loss == 0.0:
            return 100.0
        return 100.0 - 100.0 / (1.0 + avg_gain / avg_loss)

    def _compute_values(
        self, closes: List[float], bars: List[HistoricalBar]
    ) -> List[Optional[float]]:
        n = len(closes)
        out: List[Optional[float]] = [None] * n
        p = self.period
        if n <= p:
            return out

        gains = [max(closes[i] - closes[i - 1], 0.0) for i in range(1, p + 1)]
        losses = [max(closes[i - 1] - closes[i], 0.0) for i in range(1, p + 1)]
        avg_g = sum(gains) / p
        avg_l = sum(losses) / p
        out[p] = self._rsi(avg_g, avg_l)

        for i in range(p + 1, n):
            diff = closes[i] - closes[i - 1]
            g = max(diff, 0.0)
            l = max(-diff, 0.0)
            avg_g = (avg_g * (p - 1) + g) / p
            avg_l = (avg_l * (p - 1) + l) / p
            out[i] = self._rsi(avg_g, avg_l)

        return out


class RSIIndicatorV2(RSIIndicator):
    """Neutral zero/zero RSI, with immutable new identity; V1 replay untouched."""

    indicator_id = "RSI_v2"
    version = "2"

    @staticmethod
    def _rsi(avg_gain: float, avg_loss: float) -> float:
        if avg_gain == 0.0 and avg_loss == 0.0:
            return 50.0
        return RSIIndicator._rsi(avg_gain, avg_loss)


# ---------------------------------------------------------------------------
# ATR
# ---------------------------------------------------------------------------

class ATRIndicator(_BaseIndicator):
    """Average True Range — Wilder's smoothing. period >= 2."""

    indicator_id = "ATR_v1"
    version = "1"

    def __init__(self, period: int = 14) -> None:
        super().__init__(period=period)
        self.period = period
        self.min_warmup_bars = period  # first ATR at index `period`

    def _validate_params(self) -> None:
        p = dict(self._params).get("period", 0)
        if not isinstance(p, int) or p < 2:
            raise ValueError(f"ATR period must be int >= 2, got {p!r}")

    @staticmethod
    def _tr(bar: HistoricalBar, prev_close: float) -> float:
        return max(
            bar.high - bar.low,
            abs(bar.high - prev_close),
            abs(bar.low - prev_close),
        )

    def _compute_values(
        self, closes: List[float], bars: List[HistoricalBar]
    ) -> List[Optional[float]]:
        n = len(bars)
        out: List[Optional[float]] = [None] * n
        p = self.period
        if n <= p:
            return out

        trs = [self._tr(bars[i], closes[i - 1]) for i in range(1, p + 1)]
        atr = sum(trs) / p
        out[p] = atr

        for i in range(p + 1, n):
            tr = self._tr(bars[i], closes[i - 1])
            atr = (atr * (p - 1) + tr) / p
            out[i] = atr

        return out


# ---------------------------------------------------------------------------
# IndicatorLibrary
# ---------------------------------------------------------------------------

class IndicatorLibrary:
    """
    Registry and factory for research indicators.

    Usage
    -----
    ::

        lib = IndicatorLibrary()
        ind = lib.get("SMA_v1", period=20)
        results, manifest = ind.compute(
            accessor, "BTCUSDT_1h_v1", start_ms, end_ms, decision_cutoff_ms
        )
    """

    _REGISTRY: Dict[str, type] = {
        "SMA_v1": SMAIndicator,
        "EMA_v1": EMAIndicator,
        "RSI_v1": RSIIndicator,
        "RSI_v2": RSIIndicatorV2,
        "ATR_v1": ATRIndicator,
    }

    def get(self, indicator_id: str, **params: Any) -> _BaseIndicator:
        if indicator_id not in self._REGISTRY:
            raise KeyError(
                f"Unknown indicator {indicator_id!r}. "
                f"Available: {sorted(self._REGISTRY)}"
            )
        return self._REGISTRY[indicator_id](**params)  # type: ignore[return-value]

    @classmethod
    def available(cls) -> List[str]:
        return sorted(cls._REGISTRY)
