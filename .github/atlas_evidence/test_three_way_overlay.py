"""New G3 seam tested against one pinned upstream source, not a branch merge.

G3_UPSTREAM_FILE points to the independently hash-checked single module fetched
by CI. Nothing from the upstream ownership zone is added to this branch.
"""
import hashlib
import importlib.util
import json
import os
import sys
from pathlib import Path
from unittest.mock import patch
import pytest
from aql.journal.durable_journal import DurableJournal
from aql.storage.operational_store import OperationalStore
from aql.models.bar import MarketBar
from aql.paper_sim.adapter import signals_from_prospective
from aql.paper_sim.contracts import Policy
from aql.paper_sim.engine import PaperSimulator
from dataclasses import asdict

UPSTREAM="d072544427d6b08473c88b2e36d5857cfd8581dc"
MODULE_SHA256="3a72abcdf54d5186736562534e0402dfd18dc465981781edc7c0b4404fdf6fa7"
BRIDGE_SHA256="7a97c1d51e74d088d5dacaab604794005c12dc5a1d58a8b1542b794c7993f3b7"


def test_real_pinned_observer_scanner_read_to_offline_simulator(tmp_path):
    raw_path=os.environ.get("G3_UPSTREAM_FILE")
    if not raw_path:
        pytest.skip("Pinned upstream module must be supplied explicitly; no network in tests")
    path=Path(raw_path)
    assert hashlib.sha256(path.read_bytes()).hexdigest()==MODULE_SHA256
    bridge_path=path.with_name("durable_bridge_v1.py")
    assert hashlib.sha256(bridge_path.read_bytes()).hexdigest()==BRIDGE_SHA256
    bridge_spec=importlib.util.spec_from_file_location("g3_pinned_bridge",bridge_path)
    bridge=importlib.util.module_from_spec(bridge_spec);bridge_spec.loader.exec_module(bridge)
    spec=importlib.util.spec_from_file_location("g3_pinned_upstream_prospective",path)
    module=importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules,{"aql.observation.durable_bridge_v1":bridge}):
        spec.loader.exec_module(module)
    root=Path.cwd()
    fixture=json.loads((root/"tools/strategy_service_offline/fixtures/strategies.json").read_text())[0]
    journal=DurableJournal(str(tmp_path/"g1.sqlite"))
    store=OperationalStore(str(tmp_path/"store.sqlite"))
    observer=module.ProspectiveObserver(tmp_path/"g2.sqlite",journal,store,fixture,synthetic=True)
    for i in range(4):
        opened=i*900000;close=opened+899999;received=close+1
        b=MarketBar("BTCUSDT","15m",opened,close,101.,102.,100.,101.,4.,True,"binance_ws",received).with_checksum()
        with patch("time.time",return_value=(received+2)/1000):
            journal.commit(b);store.upsert(b);journal.mark_persisted(b.stable_key())
        now=received+3
        with patch.object(module,"time_ns",return_value=now*1000000):observer.tick()
    from aql.foundation.readiness import FeatureRequirement, assess
    inputs = dict(symbol="BTCUSDT", interval="15m", interval_ms=900000,
                  opens=range(0, 4*900000, 900000),
                  requirements=[FeatureRequirement("SMA", "v1", 3)],
                  available_versions={"SMA": "v1"}, clock_verified=True)
    assert assess(journal, store, decision_ms=now, **inputs)["ready"]
    assert not assess(journal, store, decision_ms=now-10, **inputs)["ready"]
    source=observer.verified_read(as_of_ms=now)
    from research_wp_r0.aql_factory_prospective_read_v1 import read_prospective_research
    # The verified upstream file is loaded under an alias by the pinned test;
    # normal imports resolve the same file in this combined candidate.
    from aql.observation.prospective import ProspectiveObserver
    reader=ProspectiveObserver(tmp_path/"g2.sqlite",journal,store,fixture,synthetic=True,read_only=True)
    factory=read_prospective_research(reader,as_of_ms=now)
    assert factory["g2_sha256"] == source["sha256"]
    assert not factory["orders_enabled"] and not factory["secretary_enqueued"]
    before={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in tmp_path.glob("*.sqlite")}
    projected=signals_from_prospective(source,expected_sha=source["sha256"],expected_run=observer.identity,
                                      as_of_ms=now)
    assert projected["signals"] and sum(projected["census"].values())==4
    sim=PaperSimulator(tmp_path/"simulation.jsonl")
    sig=projected["signals"][-1];span=sig["interval_ms"];start=(sig["decision_ms"]//span+1)*span
    w=dict(op="watch",at_ms=sig["decision_ms"],signal=sig,policy=asdict(Policy()),instance="upstream-seam")
    sid=sim.identity(w);sim.apply(sid,"w",w)
    sim.apply(sid,"a",dict(op="arm",at_ms=sig["decision_ms"]+1,mode="taker",qty="1",limit="100",
                           stop="95",target="110",expiry_ms=start+2*span-1,queue_ahead="0"))
    for i in range(2):
        t=start+i*span
        b=dict(symbol="BTCUSDT",open_ms=t,close_ms=t+span-1,received_ms=t+span,open="100",high="102" if i==0 else "112",
               low="98",close="101",final=True,clock_verified=True,synthetic=True,taker_qty="10",maker_volume="10")
        state=sim.apply(sid,str(i),dict(op="bar",at_ms=t+span,bar=b))
    assert state["phase"]=="CLOSED" and state["trading_authority"]=="NONE"
    after={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in tmp_path.glob("*.sqlite")}
    assert before==after  # adapter/simulator never writes the upstream data stores
    assert PaperSimulator(tmp_path/"simulation.jsonl").states[sid]==state
