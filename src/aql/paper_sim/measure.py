"""Measured bounded offline synthetic soak; no market/network/remote DB I/O."""
import argparse
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import platform
import statistics
import subprocess
import tempfile
import time
from .contracts import Policy, digest
from .engine import PaperSimulator


def measure(*, seconds, max_signals):
    if not 1<=seconds<=60 or not 1<=max_signals<=256:
        raise ValueError("Soak bounds: seconds 1..60, signals 1..256")
    root=Path(__file__).resolve().parents[3]
    src=Path(__file__).parent
    sig=dict(schema="aql.paper-sim.signal.v1",signal_id="a"*64,strategy_id="soak_fixture",
             strategy_version="v1",definition_sha256="b"*64,config_sha256="c"*64,
             evaluator_sha256="d"*64,source_sha256="e"*64,symbol="BTCUSDT",interval_ms=60000,
             decision_ms=60000,source_close_ms=59999,available_ms=60000,
             evidence_mode="SYNTHETIC_TESTED",trading_authority="NONE")
    latencies=[];expected={};duplicates=0;started=time.monotonic()
    with tempfile.TemporaryDirectory(prefix="g3-soak-") as directory:
        path=Path(directory)/"simulation.jsonl"
        sim=PaperSimulator(path,max_events=max_signals*4)
        while time.monotonic()-started < seconds and len(expected)<max_signals:
            w=dict(op="watch",at_ms=60000,signal=sig,policy=asdict(Policy()),instance=f"soak-{len(expected)}")
            sid=sim.identity(w)
            commands=[w,dict(op="arm",at_ms=60001,mode="taker",qty="1",limit="100",stop="95",target="110",
                             expiry_ms=299999,queue_ahead="0")]
            for i in range(2):
                start=120000+i*60000
                b=dict(symbol="BTCUSDT",open_ms=start,close_ms=start+59999,received_ms=start+60000,
                       open="100",high="102" if i==0 else "112",low="98",close="101",
                       final=True,clock_verified=True,synthetic=True,taker_qty="10",maker_volume="10")
                commands.append(dict(op="bar",at_ms=start+60000,bar=b))
            for index,command in enumerate(commands):
                t=time.perf_counter();state=sim.apply(sid,str(index),command)
                latencies.append((time.perf_counter()-t)*1000)
            assert state["phase"]=="CLOSED" and len(state["fills"])==2
            expected[sid]=digest(state)
            # Every duplicate is replayed after completion; no cost/fill reapply.
            for index,command in enumerate(commands):
                assert digest(sim.apply(sid,str(index),command))==expected[sid]
                duplicates+=1
            if len(expected)%8==0:
                sim=PaperSimulator(path,max_events=max_signals*4)
        active_elapsed=time.monotonic()-started
        t=time.perf_counter();reopened=PaperSimulator(path,max_events=max_signals*4)
        replay_ms=(time.perf_counter()-t)*1000
        actual={key:digest(state) for key,state in reopened.states.items()}
        assert actual==expected
        events=len(reopened.journal.ledger.events)
        assert events==len(expected)*4
        fills=sum(len(state["fills"]) for state in reopened.states.values())
        assert fills==len(expected)*2
        return dict(schema="aql.g3.offline-soak.v1",grade="SYNTHETIC_TESTED",
                    requested_max_seconds=seconds,requested_max_signals=max_signals,
                    measured_active_seconds=active_elapsed,elapsed_including_readback=time.monotonic()-started,
                    stop_reason="DURATION_BOUND" if active_elapsed>=seconds else "SIGNAL_CAPACITY_BOUND",
                    signals=len(expected),terminal_closed=len(actual),events=events,fills=fills,
                    duplicate_commands_verified=duplicates,unexplained_missing=0,duplicate_fills=0,
                    simulated_census={"WATCH":len(expected),"ARMED":len(expected),
                                      "TRIGGERED":len(expected),"CLOSED":len(expected)},
                    file_bytes=path.stat().st_size,replay_ms=replay_ms,
                    command_latency_ms={"median":statistics.median(latencies),
                                        "p95":sorted(latencies)[max(0,int(len(latencies)*.95)-1)],"max":max(latencies)},
                    platform=platform.platform(),source_head=subprocess.check_output(["git","rev-parse","HEAD"],cwd=root,text=True).strip(),
                    source_sha256={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(src.glob("*.py"))},
                    fixture_sha256=digest(sig),http_requests=0,remote_db_writes=0,
                    trading_authority="NONE",limits=["Measured bounded local synthetic workload, not production or 72h soak",
                    "Same-symbol instances are independent simulated books, not shared real capital",
                    "Configured fees/spread/depth/queue/adverse costs are assumptions, not venue observations",
                    "Native fsync-return evidence is not hardware power-loss or independent custody certification",
                    "Native journal replay is bounded here; no real-time host-wide resource guarantee"])


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output",type=Path,required=True)
    p.add_argument("--seconds",type=int,default=30)
    p.add_argument("--max-signals",type=int,default=128)
    a=p.parse_args();report=measure(seconds=a.seconds,max_signals=a.max_signals)
    a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_text(json.dumps(report,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({k:report[k] for k in ("signals","events","fills","measured_active_seconds","unexplained_missing")}))
