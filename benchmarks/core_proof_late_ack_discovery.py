"""Offline late-PERSISTED-ACK discovery experiment (not an SLO or live scheduler).

Compare bounded sweep settings by elapsed time from an ACK that arrives
behind the fast cursor to the first recorded proof revision.
"""
from __future__ import annotations

import argparse
import json
import tempfile
import time
from pathlib import Path

from aql.data_proof_g1_checkpoint import ProofReconcileCheckpoint, reconcile_checkpointed_page
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


def run(root: Path, *, page_size: int, pause_ms: int,
        max_wait_ms: int = 10000, rows: int = 100) -> dict:
    root.mkdir(parents=True, exist_ok=True)
    journal = DurableJournal(str(root / "journal.sqlite"))
    registry = RevisionRegistry(root / "proof.sqlite")
    progress = SweepProgress(root / "sweep.sqlite")
    fast = ProofReconcileCheckpoint(root / "fast.sqlite")
    late = bar(1)
    try:
        for i in range(rows):
            item = bar(i)
            journal.commit(item)
            if i != 1:
                journal.mark_persisted(item.stable_key())
        # Advance the fast cursor beyond the not-yet-PERSISTED row.
        for _ in range(rows + 1):
            result = reconcile_checkpointed_page(
                journal, registry, fast, symbol="BTCUSDT",
                interval="1m", limit=16)
            if result["failed_key"]:
                raise RuntimeError("fast path failed")
            if result["complete"]:
                break
        else:
            raise RuntimeError("fast cursor did not complete")
        if registry.revisions(late.stable_key()):
            raise RuntimeError("late row unexpectedly proven before ACK")
        # Start a bounded cycle, then inject ACK behind the fast cursor.
        first = run_sweep_slice(journal, registry, progress,
            symbol="BTCUSDT", interval="1m",
            page_size=page_size, max_pages=1, max_elapsed_ms=20)
        if first["failed_key"]:
            raise RuntimeError("initial sweep failed")
        start = time.perf_counter_ns()
        journal.mark_persisted(late.stable_key())
        slices = 0
        pages = 0
        deadline = start + max_wait_ms * 1_000_000
        while time.perf_counter_ns() < deadline:
            result = run_sweep_slice(journal, registry, progress,
                symbol="BTCUSDT", interval="1m",
                page_size=page_size, max_pages=2, max_elapsed_ms=20)
            slices += 1
            pages += result["pages"]
            if result["failed_key"]:
                raise RuntimeError("sweep failed: " + str(result["failed_key"]))
            if registry.revisions(late.stable_key()):
                return {"found": True,
                        "discovery_ms": round((time.perf_counter_ns() - start) / 1e6, 3),
                        "slices": slices, "pages": pages,
                        "page_size": page_size, "pause_ms": pause_ms}
            time.sleep(pause_ms / 1000)
        return {"found": False, "timeout_ms": max_wait_ms,
                "slices": slices, "pages": pages,
                "page_size": page_size, "pause_ms": pause_ms}
    finally:
        fast.close()
        progress.close()
        registry.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rows", type=int, default=100)
    args = parser.parse_args()
    if not 10 <= args.rows <= 10000:
        parser.error("rows must be 10..10000")
    with tempfile.TemporaryDirectory(prefix="aql-late-ack-") as tmp:
        root = Path(tmp)
        outcomes = [run(root / f"case_{n}", page_size=page_size,
                        pause_ms=pause_ms, rows=args.rows)
                    for n, (page_size, pause_ms) in
                    enumerate(((16, 5), (4, 50)))]
    print(json.dumps({"results": outcomes,
                      "status": "offline_observation_not_acceptance"}, indent=2))
    if not all(x["found"] for x in outcomes):
        raise SystemExit("late ACK discovery timed out")


if __name__ == "__main__":
    main()
