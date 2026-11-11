"""Focused P0 delta, actual disposable Core253, no provider or observer."""
import hashlib
from io import BytesIO
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
from zipfile import ZipFile, ZipInfo

import pytest

from research_wp_r0.aql_authenticated_historical_admission_v1 import PIN_SCHEMA
from research_wp_r0.aql_core_backbone_local_v1 import admit_local_original,query_local
from research_wp_r0.strategy_definition import StrategyDefinition
from tools.scanner_strategy_f import p0_slice as p
from tools.scanner_strategy_f.p0_delivery import Store,fixture_receive
from tools.scanner_strategy_f.secretary_factory_handoff import create_research_handoff
from tools.strategy_service_offline.common import Frozen

START = 1751328000000
STEP = p.STEP
ORIGIN = START+4*STEP


def plugin(version="v1"):
    ref = {"op":"indicator","name":"avg","field":"value","lag":0}
    definition = StrategyDefinition({
        "schema_version":"1","strategy_id":"p0_fixture","strategy_version":version,"scope":"RESEARCH_ONLY",
        "indicators":[{"name":"avg","indicator_id":"SMA_v1","version":"1","parameters":{"period":2},
                       "constraints":{"period":{"type":"int","min":2,"max":20}}}],
        "entry":{"op":"gt","left":ref,"right":{"op":"constant","value":90}},
        "exit":{"op":"lt","left":ref,"right":{"op":"constant","value":80}},
        "timing":{"decision":"CONFIRMED_CLOSE","entry_execution":"NEXT_ELIGIBLE_OPEN","ambiguity":"REJECT"},
        "risk":{"unit":"ENTRY_NOTIONAL","max_exposure":1,"max_leverage":1,
                "stop_fraction":.02,"target_fraction":.04,"entry_ttl_bars":2,"holding_bars":10}},
        registry=p.IndicatorRegistryV2()).to_dict()
    return p.native.register_strategy_plugin(definition,config_digest=p.native.manual_config_digest(definition))


def custody(root):
    n = 12
    end = START+n*STEP
    basename = "BTCUSDT-15m-2025-07"
    rows = []
    for i in range(n):
        start = START+i*STEP
        rows.append(",".join(map(str,(start,100+i,101+i,99+i,100+i,i+1,start+STEP-1,500,2,1,200,0))))
    csv = ("\n".join(rows)+"\n").encode()
    archive = BytesIO()
    with ZipFile(archive,"w") as z:
        member = ZipInfo(basename+".csv",(2025,7,1,0,0,0))
        member.create_system = 3
        z.writestr(member,csv)
    raw = archive.getvalue()
    source = hashlib.sha256(raw).hexdigest()
    checksum = (source+"  "+basename+".zip\n").encode()
    pin = dict(schema=PIN_SCHEMA,source_kind="BINANCE_KLINES_ZIP",original_object_id="P0_GENERATED",
               original_sha256=source,provenance_reference="SYNTHETIC_TEST_ONLY",
               captured_at_ms=end+10_000,claimed_available_at_ms=None,expected_inventory_sha256=None,
               vault_object_metadata=None,universe_manifest_sha256=None,universe_member_count=None,
               test_only=True,archive_name=basename+".zip",csv_member_name=basename+".csv",
               csv_member_sha256=hashlib.sha256(csv).hexdigest(),checksum_file_sha256=hashlib.sha256(checksum).hexdigest())
    spec = dict(dataset_id="TEST-ONLY-P0-BTC-15M",version=1,symbol="BTCUSDT",interval="15m",
                exchange="BINANCE",market="SPOT",source_label="native-monthly-zip",start_ms=START,
                end_exclusive_ms=end,as_of_ms=end+5000,parent_source_sha256=None,correction_reason=None,test_only=True)
    admit_local_original(root,raw,checksum,pin,spec,decision_cutoff_ms=end+2000)
    q = query_local(root,spec["dataset_id"],1,START,end,end+2000,required_source_sha256=source,sqlite_immutable=True)
    return p.seal(dict(schema="aql.scanner.p0.core-pin.v1",scope="TEST_ONLY",symbol="BTCUSDT",interval="15m",
                       dataset_id=spec["dataset_id"],version=1,source_bytes_sha256=source,
                       manifest_sha256=q["manifest_integrity_sha256"],rights="FIXTURE_RESEARCH_ONLY",
                       valid_from=0,expires=end+30*STEP,max_age_ms=3000))


def schedule(source, plugins, *, slots=4, catchup=2, symbols=("BTCUSDT",), max_bytes=1_000_000):
    source_pins = {s:source["sha256"] if s=="BTCUSDT" else p.digest(s) for s in symbols}
    return p.freeze(origin=ORIGIN,slots=slots,symbols=symbols,source_pins=source_pins,
                    plugin_pins=[item["sha256"] for item in plugins],warmup=4,catchup=catchup,
                    max_rows=slots*len(plugins)*len(symbols),max_bytes=max_bytes,lag_ms=1000)


def request(plugin, indicator="SMA_v1", period=2, version="1"):
    doc = p.seal(dict(schema="aql.scanner.p0.monitor-request.v1",symbol="BTCUSDT",
                      plugin_sha256=plugin["sha256"],indicator=indicator,parameters={"period":period},version=version))
    return doc,doc["sha256"]


@pytest.fixture
def setup(tmp_path):
    root = tmp_path/"core"
    source = custody(root)
    plug = plugin()
    plan = schedule(source,[plug])
    return plan,plug,source,root


def test_native_core_to_scanner_and_factory(setup):
    plan,plug,source,root = setup
    cutoff = ORIGIN+STEP
    query = p.source_query(source,source["sha256"],"BTCUSDT",cutoff-4*STEP,cutoff,cutoff,warehouse=root)
    event,batch = p.decision(plan,plug,"BTCUSDT",ORIGIN,cutoff,source["sha256"],query,warehouse=root)
    native = p.native.verify_factory_signal_batch(batch).data
    assert event["state"]=="ENTRY_SIGNAL" and native["event_count"]==4
    assert native["trading_authority"]=="NONE" and not native["cost_or_pnl_computed"]
    assert event["known_at"] is None
    assert (event,batch)==p.decision(plan,plug,"BTCUSDT",ORIGIN,cutoff,source["sha256"],query,warehouse=root)
    with pytest.raises(ValueError,match="P0_FROZEN_STRATEGY"):
        p.decision(plan,plugin("v2"),"BTCUSDT",ORIGIN,cutoff,source["sha256"],query,warehouse=root)


@pytest.mark.parametrize("case",["pin","rights","stale","future","symbol","revision"])
def test_source_negative_gates(setup,case):
    _,_,source,root = setup
    expected,cutoff,symbol = source["sha256"],ORIGIN+STEP,"BTCUSDT"
    candidate = dict(source)
    end = cutoff
    if case=="pin":
        candidate["source_bytes_sha256"]="0"*64
    elif case=="rights":
        candidate=p.seal({**{k:v for k,v in candidate.items() if k!="sha256"},"rights":"DENIED"})
        expected=candidate["sha256"]
    elif case=="stale":
        cutoff+=4000
    elif case=="future":
        end+=STEP
    elif case=="symbol":
        symbol="ETHUSDT"
    else:
        candidate=p.seal({**{k:v for k,v in candidate.items() if k!="sha256"},"manifest_sha256":"0"*64})
        expected=candidate["sha256"]
    with pytest.raises(ValueError):
        p.source_query(candidate,expected,symbol,ORIGIN-STEP,end,cutoff,warehouse=root)


def test_monitor_isolation_unknown_and_effects(setup,tmp_path):
    plan,plug,source,root = setup
    stores = [Store(tmp_path/name,plan,plan["sha256"]) for name in ("a","b")]
    options = [request(plug),request(plug,indicator="invalid")]
    cutoff=ORIGIN+STEP
    for store,option in zip(stores,options):
        assert len(store.poll(cutoff,[plug],{"BTCUSDT":(source,root)},{"BTCUSDT":[option]})["rows"])==1
    first,second = (store.evidence() for store in stores)
    assert first["rows"]==second["rows"] and first["native_batches"]==second["native_batches"]
    assert first["routes"]==second["routes"]=={"LAB":1,"SECRETARY":1}
    for store,state in zip(stores,("AVAILABLE","UNKNOWN")):
        with store.tx() as db:
            doc = json.loads(db.execute("SELECT raw FROM outbox WHERE route='LAB'").fetchone()[0])
            assert doc["body"]["availability"]==state
    target = tmp_path/"receiver.sqlite"
    dispatch = lambda doc:fixture_receive(target,doc)
    assert stores[0].deliver(cutoff,dispatch)=="ACKED_FIXTURE"
    assert stores[0].deliver(cutoff,dispatch)=="ACKED_FIXTURE"
    with sqlite3.connect(target) as db:
        assert db.execute("SELECT COUNT(*) FROM effects").fetchone()==(2,)


def test_disconnects_missed_and_late_never_queue_secretary(setup,tmp_path):
    plan,plug,source,root = setup
    store = Store(tmp_path/"runtime",plan,plan["sha256"])
    recovered = store.poll(ORIGIN+STEP+120_000,[plug],{"BTCUSDT":(source,root)},{})["rows"]
    assert recovered[0]["state"]=="ENTRY_SIGNAL" and recovered[0]["timing"]=="LATE_RESEARCH_ONLY"
    assert store.evidence()["routes"]=={}
    store = Store(tmp_path/"runtime",plan,plan["sha256"])
    now = ORIGIN+10*STEP
    missed = store.poll(now,[plug],{"BTCUSDT":(None,None)},{})["rows"]
    assert len(missed)==2 and all(e["state"]=="UNKNOWN" for e in missed)
    assert len(store.poll(now,[plug],{"BTCUSDT":(None,None)},{})["rows"])==1
    assert store.evidence()["expected"]==4
    with pytest.raises(ValueError,match="P0_CLOCK_REGRESSION"):
        store.poll(now-1,[plug],{"BTCUSDT":(source,root)},{})


def test_quota_storage_and_configurable_capacity(setup,tmp_path):
    _,plug,source,_ = setup
    plans = [schedule(source,[plug],symbols=("BTCUSDT",)),
             schedule(source,[plug,plugin("v2")],symbols=("BTCUSDT","ETHUSDT","PAXGUSDT"))]
    for i,plan in enumerate(plans):
        store = Store(tmp_path/f"capacity-{i}",plan,plan["sha256"])
        plugins = [plug] if i==0 else [plug,plugin("v2")]
        now = ORIGIN+4*STEP
        inputs = {s:(None,None) for s in plan["symbols"]}
        for _ in range(2):
            store.poll(now,plugins,inputs,{})
        assert store.evidence()["census"]=={"UNKNOWN":4 if i==0 else 24}
    capped = schedule(source,[plug],max_bytes=16)
    store = Store(tmp_path/"cap",capped,capped["sha256"])
    with pytest.raises(ValueError,match="P0_STORAGE_BACKPRESSURE"):
        store.poll(ORIGIN+STEP,[plug],{"BTCUSDT":(None,None)},{})
    assert store.evidence()["expected"]==0


def test_crash_after_receiver_commit_lost_ack_and_restart(setup,tmp_path):
    plan,plug,source,root = setup
    store_root = tmp_path/"runtime"
    store = Store(store_root,plan,plan["sha256"])
    now = ORIGIN+STEP
    store.poll(now,[plug],{"BTCUSDT":(source,root)},{})
    plan_path = tmp_path/"plan.json"
    plan_path.write_text(json.dumps(plan))
    target = tmp_path/"target.sqlite"
    child = """import json,os,sys
from pathlib import Path
from tools.scanner_strategy_f.p0_delivery import Store,fixture_receive
plan=json.loads(Path(sys.argv[1]).read_bytes())
s=Store(sys.argv[2],plan,plan['sha256'])
s.deliver(int(sys.argv[4]),lambda doc:fixture_receive(sys.argv[3],doc),fault=lambda:os._exit(73))
"""
    proc = subprocess.run([sys.executable,"-B","-c",child,str(plan_path),str(store_root),str(target),str(now)],
                          capture_output=True,timeout=30)
    assert proc.returncode==73,proc.stderr.decode()
    restarted = Store(store_root,plan,plan["sha256"])
    assert restarted.evidence()["delivery"]=={"PENDING":1}
    assert restarted.deliver(now+999,lambda d:fixture_receive(target,d))=="IDLE"
    assert restarted.deliver(now+1000,lambda d:fixture_receive(target,d))=="ACKED_FIXTURE"
    with sqlite3.connect(target) as db:
        assert db.execute("SELECT COUNT(*) FROM effects").fetchone()==(1,)
    assert restarted.evidence()["expected"]==1


def test_consumer_down_and_malformed_ack(setup,tmp_path):
    plan,plug,source,root = setup
    now = ORIGIN+STEP
    store = Store(tmp_path/"runtime",plan,plan["sha256"])
    store.poll(now,[plug],{"BTCUSDT":(source,root)},{})
    def down(_):
        raise OSError("fixture receiver unavailable")
    assert store.deliver(now,down,max_attempts=1)=="PENDING"
    assert store.deliver(now+1000,down,max_attempts=1)=="QUARANTINED"
    other = Store(tmp_path/"other",plan,plan["sha256"])
    other.poll(now,[plug],{"BTCUSDT":(source,root)},{})
    assert other.deliver(now,lambda _:{"fake":True})=="QUARANTINED"


def test_receiver_contract_and_crash_before_persist(setup,tmp_path):
    plan,plug,source,root = setup
    now = ORIGIN+STEP
    store = Store(tmp_path/"runtime",plan,plan["sha256"])
    event = store.poll(now,[plug],{"BTCUSDT":(source,root)},{})["rows"][0]
    with pytest.raises(ValueError,match="F3_SOURCE_AND_POLICY_GRAPH_NOT_READY_FOR_PROPOSAL"):
        create_research_handoff(Frozen.build(event).receipt())
    target = tmp_path/"effect.sqlite"
    invalid = store._envelope("LAB",event)
    with pytest.raises(ValueError,match="P0_RECEIVER_SCOPE"):
        fixture_receive(target,invalid)
    def crash(_):
        raise SystemExit(74)
    with pytest.raises(SystemExit,match="74"):
        store.deliver(now,crash)
    assert not target.exists()
    assert store.poll(now,[plug],{"BTCUSDT":(source,root)},{})["rows"]==[]
    assert store.deliver(now+1000,lambda doc:fixture_receive(target,doc))=="ACKED_FIXTURE"


def test_missing_window_and_warmup(setup,tmp_path):
    plan,plug,source,root = setup
    now = ORIGIN+STEP
    available = Store(tmp_path/"available",plan,plan["sha256"])
    available.poll(now,[plug],{"BTCUSDT":(source,root)},{"BTCUSDT":[request(plug,period=8)]})
    missing = Store(tmp_path/"missing",plan,plan["sha256"])
    missing.poll(now,[plug],{"BTCUSDT":(None,None)},{"BTCUSDT":[request(plug)]})
    for store, reason in [(available,"WARMUP"),(missing,"SOURCE_UNKNOWN")]:
        with store.tx() as db:
            lab = json.loads(db.execute("SELECT raw FROM outbox WHERE route='LAB'").fetchone()[0])["body"]
        assert lab["availability"]=="UNKNOWN" and lab["reason"]==reason
    assert missing.evidence()["census"]=={"UNKNOWN":1}


def test_unacked_secretary_signal_expires_before_dispatch(setup,tmp_path):
    plan,plug,source,root = setup
    now = ORIGIN+STEP
    store = Store(tmp_path/"expiry",plan,plan["sha256"])
    store.poll(now,[plug],{"BTCUSDT":(source,root)},{})
    assert store.deliver(now+plan["lag_ms"]+1,lambda _:pytest.fail("stale dispatch"))=="EXPIRED"
    assert store.evidence()["delivery"]=={"EXPIRED":1}
    assert store.evidence()["census"]=={"ENTRY_SIGNAL":1}


@pytest.mark.parametrize("order",["duplicate","reversed"])
def test_reject_duplicate_and_disordered_core_bars(setup,order):
    _,_,source,root = setup
    now = ORIGIN+STEP
    query = p.source_query(source,source["sha256"],"BTCUSDT",now-4*STEP,now,now,warehouse=root)
    bars = query["bars"]
    query["bars"] = [bars[0],*bars[:-1]] if order=="duplicate" else list(reversed(bars))
    query["query_sha256"] = p.digest({key:value for key,value in query.items() if key!="query_sha256"})
    with pytest.raises(ValueError,match="H_BAR_DUPLICATE_MISSING_OR_FUTURE"):
        p.source_query(source,source["sha256"],"BTCUSDT",now-4*STEP,now,now,
                       warehouse=root,reader=lambda *args,**kwargs:query)
