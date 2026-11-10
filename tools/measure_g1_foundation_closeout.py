"""Offline synthetic G1 resource receipt; no provider or database connections.

Run from checkout: python -B tools/measure_g1_foundation_closeout.py --output PATH
"""
import argparse
import hashlib
import json
from pathlib import Path
import platform
import statistics
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from aql.foundation.census import census
from aql.foundation.scheduler import AdaptiveScheduler, Job
from aql.foundation.readiness import assess, FeatureRequirement
from aql.recovery.rest_budget import RestBudget
from aql.journal.durable_journal import DurableJournal
from aql.storage.operational_store import OperationalStore
from aql.lanes import JournalConsumer
from aql.models.bar import MarketBar


def measure():
    start = time.perf_counter()
    metadata = {"symbols": [dict(symbol=f"SYM{i}USDT", status="TRADING",
                                 isSpotTradingAllowed=True) for i in range(8)]}
    now = int(time.time()*1000)
    universe = census(metadata, observed_ms=now, decision_ms=now)
    api = RestBudget(limit=1200, reserve=100)
    db = RestBudget(limit=512, reserve=64)
    scheduler = AdaptiveScheduler(api, db, capacity=320, core_reserve=32, max_batch=16)
    for i in range(256):
        assert scheduler.submit(Job(str(i), 0 if i < 16 else 1, 2, 1))
    with tempfile.TemporaryDirectory(prefix="g1-foundation-") as directory:
        root = Path(directory)
        journal = DurableJournal(str(root / "journal.sqlite"))
        store = OperationalStore(str(root / "store.sqlite"))
        latencies = []
        admitted = []
        while scheduler.identities:
            jobs = scheduler.take(pressure=.1)
            assert jobs, "Fixture must fit declared API/DB budget"
            for job in jobs:
                i = int(job.identity)
                opened = (i // 8)*60000
                b = MarketBar(f"SYM{i%8}USDT", "1m", opened, opened+59999,
                              10.,11.,9.,10.,1.,True,"synthetic-budget",now).with_checksum()
                t = time.perf_counter(); journal.commit(b)
                latencies.append((time.perf_counter()-t)*1000)
                admitted.append(job.identity)
        for symbol in metadata["symbols"]:
            consumer = JournalConsumer(journal,store,symbol["symbol"],"1m",batch_size=16)
            while consumer.drain_once(): pass
        decision = int(time.time()*1000)+1
        readiness = [assess(journal,store,symbol=row["symbol"],interval="1m",
                           opens=range(0,32*60000,60000),
                           requirements=[FeatureRequirement("SMA","v1",32)],
                           available_versions={"SMA":"v1"},decision_ms=decision,
                           clock_verified=True) for row in metadata["symbols"]]
        assert all(r["ready"] for r in readiness)
        assert store.count() == 256
        assert len(set(admitted)) == 256
        sizes = {p.name:p.stat().st_size for p in root.iterdir() if p.is_file()}
        report = dict(schema="aql.g1.resource-receipt.v1", grade="SYNTHETIC_TESTED",
                      base_sha=subprocess.check_output(["git","merge-base","HEAD","origin/main"],cwd=ROOT,text=True).strip(),
                      tested_tree_sha=subprocess.check_output(["git","write-tree"],cwd=ROOT,text=True).strip(),
                      platform=platform.platform(), python=sys.version.split()[0],
                      rows=256, symbols=8, census=universe,
                      scheduler=scheduler.metrics, simulated_api_weight=api.used,
                      actual_http_requests=0, remote_db_writes=0,
                      local_store_rows=store.count(), local_file_bytes=sizes,
                      local_total_bytes=sum(sizes.values()),
                      commit_ms=dict(median=statistics.median(latencies),
                                     p95=sorted(latencies)[int(len(latencies)*.95)-1],max=max(latencies)),
                      elapsed_seconds=time.perf_counter()-start,
                      all_decisions_source_ready=True,
                      source_sha256={str(p.relative_to(ROOT)).replace("\\","/"):hashlib.sha256(p.read_bytes()).hexdigest()
                                     for p in sorted((ROOT/"src/aql/foundation").glob("*.py"))},
                      limits=["Synthetic metadata, bars and clock trust; no current Binance census or live budget measurement",
                              "API weights and DB write units are configured assumptions; local SQLite bytes/time are measured",
                              "DB reservation counts logical jobs, not SQLite physical statements/fsyncs",
                              "No Supabase sandbox or production integration verified",
                              "Per-process cooperative scheduling, not host-wide resource enforcement",
                              "Source readiness only; indicator computation remains in existing versioned library"])
        return report


if __name__ == "__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output",type=Path,required=True)
    args=parser.parse_args()
    report=measure()
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(report,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({k:report[k] for k in ("rows","symbols","actual_http_requests","local_total_bytes","commit_ms")}))
