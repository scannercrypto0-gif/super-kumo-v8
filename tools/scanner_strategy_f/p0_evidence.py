"""Run and compare two independent disposable Scanner P0 fixture processes."""
import argparse
from contextlib import closing
import hashlib
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
from tempfile import TemporaryDirectory
import time
import tracemalloc

from tools.scanner_strategy_f.p0_delivery import Store, canonical, fixture_receive
from tools.scanner_strategy_f.test_p0_slice import ORIGIN, STEP, custody, plugin, request, schedule
from tools.scanner_strategy_f.p0_stage import PINS


def peak_rss_bytes():
    if sys.platform == "win32":
        import ctypes
        from ctypes import wintypes

        class ProcessMemory(ctypes.Structure):
            _fields_ = [
                ("size", wintypes.DWORD), ("page_faults", wintypes.DWORD),
                *((name, ctypes.c_size_t) for name in (
                    "peak_working_set", "working_set", "peak_paged_pool", "paged_pool",
                    "peak_nonpaged_pool", "nonpaged_pool", "pagefile", "peak_pagefile",
                )),
            ]

        process = ctypes.windll.kernel32.GetCurrentProcess
        process.restype = wintypes.HANDLE
        counters = ProcessMemory()
        counters.size = ctypes.sizeof(counters)
        get_memory = ctypes.windll.psapi.GetProcessMemoryInfo
        get_memory.argtypes = (wintypes.HANDLE, ctypes.POINTER(ProcessMemory), wintypes.DWORD)
        if not get_memory(process(), ctypes.byref(counters), counters.size):
            raise ctypes.WinError()
        return counters.peak_working_set

    import resource

    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return peak if sys.platform == "darwin" else peak * 1024


def replay(root):
    tracemalloc.start()
    wall, cpu = time.monotonic_ns(), time.process_time_ns()
    warehouse = root/"core"
    source = custody(warehouse)
    strategy = plugin()
    plan = schedule(source,[strategy])
    store = Store(root/"scanner",plan,plan["sha256"])
    target = root/"effects.sqlite"
    latencies = []
    for i in range(plan["slots"]):
        now = ORIGIN+(i+1)*STEP
        poll = store.poll(now,[strategy],{"BTCUSDT":(source,warehouse)},{"BTCUSDT":[request(strategy)]})
        assert len(poll["rows"])==1
        latencies.append(poll["wall_us"])
        for _ in range(2):
            assert store.deliver(now,lambda doc:fixture_receive(target,doc))=="ACKED_FIXTURE"
        assert store.deliver(now,lambda _: None)=="IDLE"
    ledger = store.evidence()
    with closing(sqlite3.connect(target)) as db:
        effects = [row[0] for row in db.execute("SELECT id FROM effects ORDER BY id")]
    with store.tx() as db:
        acknowledgements = [json.loads(raw)["sha256"] for raw, in db.execute("SELECT ack FROM outbox ORDER BY id")]
    assert ledger["expected"]==4 and ledger["delivery"]=={"ACKED":8} and len(effects)==8
    assert len(ledger["native_batches"])==4 and ledger["routes"]=={"LAB":4,"SECRETARY":4}
    proof = dict(scope="TEST_ONLY",authority="NONE",source=source,plan=plan,ledger=ledger,
                 effects=effects,acknowledgements=acknowledgements,provider_requests=0,dependency_heads=PINS)
    return dict(proof=proof,proof_sha256=hashlib.sha256(canonical(proof)).hexdigest(),
                metrics=dict(wall_us=(time.monotonic_ns()-wall)//1000,cpu_us=(time.process_time_ns()-cpu)//1000,
                             python_allocation_peak_bytes=tracemalloc.get_traced_memory()[1],
                             process_peak_rss_bytes=peak_rss_bytes(),
                             poll_wall_us=latencies,decision_bytes=ledger["decision_bytes"]))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output",type=Path)
    parser.add_argument("--child",action="store_true")
    parser.add_argument("--head")
    args = parser.parse_args()
    if args.child:
        with TemporaryDirectory(prefix="scanner-p0-") as scratch:
            args.output.write_bytes(canonical(replay(Path(scratch))))
        return
    args.output.mkdir(parents=True,exist_ok=True)
    results = []
    for n in (1,2):
        path = args.output.resolve()/f"replay-{n}.json"
        subprocess.run([sys.executable,"-B","-m",__spec__.name,str(path),"--child"],check=True,timeout=120)
        results.append(json.loads(path.read_bytes()))
    assert results[0]["proof"]==results[1]["proof"]
    summary = dict(head=args.head,proof_sha256=results[0]["proof_sha256"],
                   replays=[r["metrics"] for r in results])
    (args.output/"summary.json").write_bytes(canonical(summary))
    print(json.dumps(summary))


if __name__=="__main__":
    main()
