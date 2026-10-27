"""Manual, non-gating benchmark: G1 journal write latency with/without sweep.

Run locally with: python -m benchmarks.core_proof_sweep_latency
Not a CI performance gate: runner noise and SQLite storage vary by machine.
"""
from __future__ import annotations

import json
import statistics
import tempfile
import threading
import time
from pathlib import Path

from aql.data_proof_g1_sweep_progress import SweepProgress, run_sweep_slice
from aql.data_proof_registry import RevisionRegistry
from aql.journal.durable_journal import DurableJournal
from aql.models.bar import MarketBar


def bar(i: int) -> MarketBar:
    return MarketBar(symbol="BTCUSDT", interval="1m",
        bar_open=i * 60000, bar_close=i * 60000 + 59999,
        open=1., high=2., low=1., close=2., volume=5.,
        is_final=True, source="binance_ws",
        ingested_at=i * 60000 + 60001).with_checksum()


def percentile(values: list[float], pct: float) -> float:
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int((len(ordered) - 1) * pct))]


def trial(root: Path, with_sweep: bool, *, warmup: int = 100,
          measured: int = 500) -> dict:
    root.mkdir(parents=True, exist_ok=True)
    journal = DurableJournal(str(root / "journal.sqlite"))
    registry = RevisionRegistry(root / "proof.sqlite")
    progress = SweepProgress(root / "sweep.sqlite")
    for i in range(warmup):
        item = bar(i)
        journal.commit(item)
        journal.mark_persisted(item.stable_key())
    stop = threading.Event()
    errors: list[str] = []

    def sweep():
        try:
            while not stop.is_set():
                run_sweep_slice(journal, registry, progress,
                    symbol="BTCUSDT", interval="1m", page_size=16,
                    max_pages=2, max_elapsed_ms=20)
                stop.wait(0.005)
        except Exception as exc:
            errors.append(repr(exc))
            stop.set()

    worker = threading.Thread(target=sweep, daemon=True)
    if with_sweep:
        worker.start()
    samples: list[float] = []
    try:
        for i in range(warmup, warmup + measured):
            if errors:
                raise RuntimeError(errors[0])
            item = bar(i)
            start = time.perf_counter_ns()
            journal.commit(item)
            journal.mark_persisted(item.stable_key())
            samples.append((time.perf_counter_ns() - start) / 1_000_000)
    finally:
        stop.set()
        if with_sweep:
            worker.join(timeout=10)
            if worker.is_alive():
                raise RuntimeError("sweep thread did not stop")
        progress.close()
        registry.close()
    if errors:
        raise RuntimeError(errors[0])
    return {"count": len(samples), "p50_ms": percentile(samples, 0.50),
            "p95_ms": percentile(samples, 0.95),
            "p99_ms": percentile(samples, 0.99),
            "max_ms": max(samples),
            "mean_ms": statistics.mean(samples)}


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="aql-proof-perf-") as tmp:
        root = Path(tmp)
        baseline = trial(root / "baseline", False)
        sweep = trial(root / "sweep", True)
        ratios = {k: round(sweep[k] / baseline[k], 3)
                  for k in ("p50_ms", "p95_ms", "p99_ms")
                  if baseline[k] > 0}
        print(json.dumps({"baseline": baseline, "with_sweep": sweep,
                          "ratios": ratios,
                          "status": "observational_only_not_acceptance"},
                         indent=2))


if __name__ == "__main__":
    main()
