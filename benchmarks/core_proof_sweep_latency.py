"""Manual, non-gating benchmark: G1 journal write latency with/without sweep.

Run locally with: python -m benchmarks.core_proof_sweep_latency
Not a CI performance gate: runner noise and SQLite storage vary by machine.
"""
from __future__ import annotations

import json
import argparse
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
          measured: int = 500, page_size: int = 16,
          pause_ms: int = 5) -> dict:
    root.mkdir(parents=True, exist_ok=True)
    journal = DurableJournal(str(root / "journal.sqlite"))
    for i in range(warmup):
        item = bar(i)
        journal.commit(item)
        journal.mark_persisted(item.stable_key())
    stop = threading.Event()
    errors: list[str] = []

    def sweep():
        registry = None
        progress = None
        try:
            registry = RevisionRegistry(root / "proof.sqlite")
            progress = SweepProgress(root / "sweep.sqlite")
            while not stop.is_set():
                run_sweep_slice(journal, registry, progress,
                    symbol="BTCUSDT", interval="1m", page_size=page_size,
                    max_pages=2, max_elapsed_ms=20)
                stop.wait(pause_ms / 1000)
        except Exception as exc:
            errors.append(repr(exc))
            stop.set()
        finally:
            if progress is not None:
                progress.close()
            if registry is not None:
                registry.close()

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
    if errors:
        raise RuntimeError(errors[0])
    return {"count": len(samples), "p50_ms": percentile(samples, 0.50),
            "p95_ms": percentile(samples, 0.95),
            "p99_ms": percentile(samples, 0.99),
            "max_ms": max(samples),
            "mean_ms": statistics.mean(samples)}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--page-size", type=int, default=16)
    parser.add_argument("--pause-ms", type=int, default=5)
    args = parser.parse_args()
    if not 1 <= args.page_size <= 1024 or not 0 <= args.pause_ms <= 1000:
        parser.error("page-size must be 1..1024 and pause-ms 0..1000")
    # Counterbalance warm-cache/order effects: AB then BA, separate databases.
    runs = []
    with tempfile.TemporaryDirectory(prefix="aql-proof-perf-") as tmp:
        root = Path(tmp)
        for repeat, order in enumerate(((False, True), (True, False)), start=1):
            pair = {}
            for position, with_sweep in enumerate(order):
                label = "with_sweep" if with_sweep else "baseline"
                pair[label] = trial(root / f"r{repeat}_p{position}_{label}",
                                    with_sweep, page_size=args.page_size,
                                    pause_ms=args.pause_ms)
            ratios = {k: round(pair["with_sweep"][k] / pair["baseline"][k], 3)
                      for k in ("p50_ms", "p95_ms", "p99_ms")
                      if pair["baseline"][k] > 0}
            runs.append({"order": ["with_sweep" if x else "baseline"
                                    for x in order],
                         **pair, "ratios": ratios})
    print(json.dumps({"configuration": {"page_size": args.page_size,
                                      "pause_ms": args.pause_ms},
                      "runs": runs,
                      "status": "observational_only_not_acceptance",
                      "caution": "two sequential matched pairs; no SLO inference"},
                     indent=2))


if __name__ == "__main__":
    main()
