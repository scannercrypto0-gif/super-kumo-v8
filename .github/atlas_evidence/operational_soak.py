"""Paced isolated G3 service exercise. Market inputs are scripted, no live authority."""
import hashlib
import json
import subprocess
import sys
import tempfile
import time
from collections import Counter
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from test_engine import arm, candle, watch
from aql.paper_sim.engine import PaperSimulator

def utc():
    return datetime.now(timezone.utc).isoformat()

def main():
    expected = {}
    counts = Counter()
    timeline = []
    replays = failures = events = fills = 0
    started = time.monotonic()
    start_utc = utc()
    with tempfile.TemporaryDirectory() as tmp:
        ledger = Path(tmp) / "paper.jsonl"
        sim = PaperSimulator(ledger)
        for i in range(60):
            time.sleep(max(0, started + i + 1 - time.monotonic()))
            w = watch(instance=f"operational-soak-{i}")
            sid = sim.identity(w)
            kind = i % 5
            options = [{}, {"mode":"maker","limit":"99","queue_ahead":"2"},
                       {"mode":"maker","limit":"97","expiry_ms":179999}, {}, {}][kind]
            tail = [
                [candle(), candle(180000, high="112", low="99", close="111")],
                [candle(low="98", maker_volume="2"), candle(180000, low="98", maker_volume=".4"),
                 dict(op="cancel",at_ms=240001), candle(240000, high="112",low="99",close="111")],
                [candle(low="98"), dict(op="expire",at_ms=180001)],
                [candle(low="94", high="111")],
                [dict(op="expire",at_ms=300000)],
            ][kind]
            commands = [w, arm(**options), *tail]
            if i in (19, 39, 59):
                code = ("from aql.paper_sim.engine import PaperSimulator;"
                        "import json,os,sys;"
                        "s=PaperSimulator(sys.argv[1],post_commit=lambda:os._exit(23));"
                        "s.apply(sys.argv[2],'0',json.loads(sys.argv[3]))")
                child = subprocess.run([sys.executable,"-B","-c",code,str(ledger),sid,json.dumps(w)],
                                       capture_output=True, timeout=8)
                assert child.returncode == 23, child.stderr
                failures += 1
                sim = PaperSimulator(ledger)
                assert sim.states[sid]["phase"] == "WATCH"
            for j, command in enumerate(commands):
                state = sim.apply(sid, str(j), command)
                if kind == 1 and j == 2:
                    assert state["filled"] == "0"
                if kind == 1 and j == 3:
                    assert Decimal(state["filled"]) == Decimal(".4")
            phase = ["CLOSED","CLOSED","NO_FILL","UNKNOWN","UNKNOWN"][kind]
            assert state["phase"] == phase and state["trading_authority"] == "NONE"
            assert len(state["fills"]) == [2,2,0,1,0][kind]
            if kind == 0:
                assert Decimal(state["fees"]) == (Decimal("100.03")+Decimal("109.967")) * Decimal(".001")
            if kind == 1:
                assert Decimal(state["adverse_cost"]) == Decimal(".00396")
            if phase == "UNKNOWN":
                assert state["net_pnl"] is None
            before = ledger.read_bytes()
            for j, command in enumerate(commands):
                assert sim.apply(sid, str(j), command) == state
                replays += 1
            assert ledger.read_bytes() == before
            expected[sid] = state
            counts[phase] += 1
            events += len(commands)
            fills += len(state["fills"])
            timeline.append({"signal":sid,"phase":phase,"utc":utc(),"source_available_ms":w["signal"]["available_ms"],
                             "events":len(commands),"fills":len(state["fills"]),"fees":state["fees"],
                             "adverse_cost":state["adverse_cost"],"reason":state["reason"]})
        reopened = PaperSimulator(ledger)
        assert reopened.states == expected
        assert len(reopened.journal.ledger.events) == events == replays
        elapsed = time.monotonic() - started
        assert elapsed >= 60
        print(json.dumps({"started_utc":start_utc,"ended_utc":utc(),"elapsed_seconds":elapsed,
                         "source":"scripted market inputs; real paced writes and process faults",
                         "signals":len(expected),"phases":dict(counts),"events":events,"fills":fills,
                         "verified_retries":replays,"post_fsync_process_exits":failures,
                         "unexplained_missing":0,"duplicate_effects":0,"trading_authority":"NONE",
                         "journal_sha256":hashlib.sha256(ledger.read_bytes()).hexdigest(),
                         "timeline":timeline},indent=2))

if __name__ == "__main__":
    main()
