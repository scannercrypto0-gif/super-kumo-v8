"""New Core delta with the actual pinned Discoverer consumer."""
from concurrent.futures import ThreadPoolExecutor
import ast
from copy import deepcopy
import io
import os
from pathlib import Path
import subprocess
import sys
import tarfile
import types

import pytest

from aql.archive.contracts import digest
from aql.archive.discoverer_view import DiscovererView, factory_inputs, seal
from aql.archive.source_poll import PollFence
from aql.archive.source_registry import admit_vintage
from aql.archive.scanner_view import scanner_monitor_view
from aql.archive.source_view import as_of_view

D = "9b60eb00aa890ecbd7e617925896e02963c1b5e3"
F = "04b63cc9b406b1f3eae2ac7de5d43ebda26dbfdf"
S = "ccf57ad3db7e71290a8321840e800136567e3af4"
MEMBERS = {"BTC":{"sector":"benchmark","rank_eligible":False},
           "PAXG":{"sector":"gold","rank_eligible":False},
           "ALT":{"sector":"application","rank_eligible":True}}


def git(*args):
    return subprocess.check_output(["git",*args])


@pytest.fixture(scope="module")
def discoverer(tmp_path_factory):
    path = tmp_path_factory.mktemp("pinned-overlay")
    raw = git("archive",D,"tools/strategy_discoverer_offline")
    with tarfile.open(fileobj=io.BytesIO(raw)) as archive:
        archive.extractall(path,filter="data")
    import tools
    tools.__path__.append(str(path/"tools"))
    from tools.strategy_discoverer_offline import continuous_research
    assert Path(continuous_research.__file__).is_relative_to(path)
    return continuous_research


def inventory(slots=(200,300,400,500)):
    series = []
    for symbol in MEMBERS:
        for feature in ("outcome","liquidity","news","monitor"):
            source = "FIXTURE:"+feature
            market = {"venue":"BINANCE","market":"SPOT","subject":symbol}
            rights = dict(source=source,state="VERIFIED",uses=["MONITOR_ONLY"],valid_from=0,expires_at=10_000)
            rights_pin = digest(rights)
            item = dict(symbol=symbol,feature=feature,source=source,market=market,status="ADMITTED",
                        retention_until_ms=9000,
                        definition=dict(id="fixture:"+feature,version=1,unit="FIXTURE_SCORE",scale=1,
                                        operation="SIGNED_INTEGER_AT_DECLARED_SCALE"),
                        records=[],pins={},rights={rights_pin:rights})
            def append(key,value,version,prior,event,pub,recv,commit):
                doc = dict(key=key,version=version,prior=prior,source=source,market=market,use="MONITOR_ONLY",
                           grade="TEST_ONLY",value=value,final=True,event_at=event,published_at=pub,received_at=recv,
                           committed_at=commit,known_at=None,witness=None,rights=rights_pin)
                pin = digest(doc)
                item["records"].append(doc)
                item["pins"].setdefault(key,{})[str(version)] = pin
                return pin
            for slot in slots:
                onset = slot-100
                if feature == "outcome":
                    bps = {"ALT":200,"BTC":-200}.get(symbol,0) if slot in (200,500) else 0
                    if slot==200 and symbol=="PAXG":
                        continue
                    append(f"outcome:{slot}",dict(return_bps=bps,onset=onset,end=slot-3),
                           1,None,slot-3,slot-2,slot-1,slot)
                elif feature == "news":
                    append(f"context:{onset}",9,1,None,onset-10,onset+1,onset+2,onset+3)
                else:
                    pin = append(f"context:{onset}",2,1,None,onset-10,onset-8,onset-6,onset-4)
                    if feature=="liquidity":
                        append(f"context:{onset}",-2,2,pin,onset-10,onset-2,onset-1,onset)
            series.append(item)
    return seal(dict(schema="aql.core.discoverer-inventory.v1",mode="TEST_ONLY",venue="BINANCE",market="SPOT",
                     members=MEMBERS,membership_effective=1,membership_expires=5000,series=series))


def view(data=None,access=1000):
    data = inventory() if data is None else data
    return DiscovererView(data,data["sha256"],access_ms=access)


def reseal(doc):
    return seal({k:v for k,v in doc.items() if k!="sha256"})


def plan_for(d):
    return d.policy(origin=200,step=100,members=MEMBERS)


def test_real_pinned_discoverer_gain_loss_quiet_and_factory_boundary(discoverer,tmp_path):
    d = discoverer
    p = plan_for(d)
    repository = view()
    loop = d.Loop(tmp_path/"run",p,p["sha256"])
    evidence = {}
    def context(query):
        doc,proof = repository.context(query,query["sha256"])
        evidence[query["symbol"]] = proof
        assert proof["unavailable"]["news"] == "NOT_AVAILABLE_BY_CUTOFF"
        assert next(r for r in proof["records"] if r["feature"]=="liquidity")["original"]["version"] == 1
        assert all(r["original"]["known_at"] is None for r in proof["records"])
        return doc,doc["sha256"]
    def run(slot):
        snapshot,proof = repository.snapshot(slot,p,p["sha256"])
        assert proof["availability_basis"] == "SYNTHETIC_COMMIT_CLOCK_ONLY"
        return loop.tick(slot,snapshot,snapshot["sha256"],context)
    initial = run(200)
    assert initial["watch"]["census"] == {"UP":1,"DOWN":1,"UNKNOWN":1}
    quiet = run(300)
    assert quiet["watch"]["census"] == {"NO_EVENT":3}
    assert {c["comparison"]["direction"] for c in quiet["candidates"]} == {"UP","DOWN"}
    assert quiet == run(300)
    factory = types.ModuleType("pinned_factory")
    raw = git("show",F+":research_wp_r0/aql_factory_e_research_results_store_v1.py")
    exec(compile(raw,"factory_registry.py","exec"),factory.__dict__)
    for candidate in quiet["candidates"]:
        packet = factory_inputs(candidate,candidate["sha256"],evidence["ALT"],evidence["ALT"]["sha256"])
        assert packet["availability"]=="ADMITTED" and packet["rule"]["operator"]=="GE"
        assert packet["evaluation"]=="FACTORY_OWNED_NOT_RUN"
        with pytest.raises(factory.ResultsStoreError,match="SCHEMA_OR_PROMOTION"):
            factory.register_experiment(tmp_path/"must-not-create.sqlite",packet)
        assert not (tmp_path/"must-not-create.sqlite").exists()


def test_revised_news_unknown_and_source_rights(discoverer):
    p = plan_for(discoverer)
    query = discoverer.context_query(p,{"symbol":"ALT","onset":100})
    data = inventory()
    liq = next(s for s in data["series"] if s["symbol"]=="ALT" and s["feature"]=="liquidity")
    right = dict(next(iter(liq["rights"].values())),state="DENIED")
    pin = digest(right)
    liq["rights"][pin] = right
    original = liq["records"][0]
    original["rights"] = pin
    liq["pins"]["context:100"]["1"] = digest(original)
    revision = liq["records"][1]
    revision["prior"] = digest(original)
    liq["pins"]["context:100"]["2"] = digest(revision)
    fixture,evidence = view(reseal(data)).context(query,query["sha256"])
    assert evidence["unavailable"]["liquidity"] == "RIGHTS_UNAVAILABLE"
    assert evidence["unavailable"]["news"] == "NOT_AVAILABLE_BY_CUTOFF"
    assert all(r["feature"] not in ("liquidity","news") for r in fixture["records"])
    _,expired = view(access=9500).context(query,query["sha256"])
    assert expired["unavailable"]["liquidity"] == "RETENTION_EXPIRED"


def test_visible_revision_preserves_parent(discoverer):
    query = discoverer.context_query(plan_for(discoverer),{"symbol":"ALT","onset":100})
    data = inventory()
    series = next(s for s in data["series"] if (s["symbol"],s["feature"])==("ALT","liquidity"))
    changed = series["records"][1]
    changed["committed_at"] = 99
    series["pins"]["context:100"]["2"] = digest(changed)
    fixture,proof = view(reseal(data)).context(query,query["sha256"])
    values = [row for row in fixture["records"] if row["feature"]=="liquidity"]
    assert [r["version"] for r in values] == [1,2] and values[1]["parent_sha256"]==values[0]["source_sha256"]
    assert discoverer.precursor(query,fixture,fixture["sha256"])["features"]["liquidity"]["value"] == -2
    assert proof["records"][1]["rights_receipt"]["state"]=="VERIFIED"


def test_wrong_market_stale_membership_and_tamper(discoverer):
    p = plan_for(discoverer)
    original = inventory()
    altered = deepcopy(original)
    altered["series"][0]["records"][0]["value"]["return_bps"] = 999
    with pytest.raises(ValueError,match="MANIFEST_PIN"):
        DiscovererView(altered,original["sha256"],access_ms=1000)
    with pytest.raises(ValueError,match="SOURCE_DIGEST"):
        view(reseal(altered)).snapshot(200,p,p["sha256"])
    query = discoverer.context_query(p,{"symbol":"BTC","onset":100})
    forged = reseal({**query,"venue":"OTHER"})
    with pytest.raises(ValueError,match="CONTEXT_REQUEST_SCOPE"):
        view().context(forged,forged["sha256"])
    with pytest.raises(ValueError,match="FUTURE_ASOF"):
        view().snapshot(1001,p,p["sha256"])
    with pytest.raises(ValueError,match="STALE_OR_MISSING_MEMBERSHIP"):
        view(access=7000).snapshot(6000,p,p["sha256"])
    prod = reseal({**original,"mode":"SOURCE_EVIDENCE"})
    assert view(prod).context(query,query["sha256"])[0] is None
    with pytest.raises(ValueError,match="DISCOVERER_FIXTURE_CONSUMER_ONLY"):
        view(prod).snapshot(200,p,p["sha256"])


def test_registry_and_vintage_admission():
    item = inventory()["series"][0]
    observation = item["records"][0]
    rights = item["rights"][observation["rights"]]
    entry = dict(status="ADMITTED",market=item["market"],mode="TEST_ONLY",terms_sha256="1"*64,
                 region="FIXTURE",rights_sha256=observation["rights"],use="MONITOR_ONLY",retention_until_ms=9000)
    registry = seal(dict(schema="aql.core.source-registry.v1",authority="NONE",sources={item["source"]:entry}))
    def admit(doc,at):
        return admit_vintage(registry,registry["sha256"],doc,digest(doc),rights,digest(rights),access_ms=at)
    assert admit(observation,1000)["status"]=="ADMITTED"
    assert admit(observation,9000)["reason"]=="RIGHTS_OR_RETENTION_EXPIRED"
    assert admit({**observation,"final":False},1000)["reason"]=="VINTAGE_NOT_FINAL_OR_CLOCK_UNKNOWN"
    assert admit({**observation,"source":"NOT_REGISTERED"},1000)["reason"]=="BLOCKED_SOURCE"


@pytest.mark.parametrize("header",["NaN","-5","Infinity",None])
def test_429_bad_header_has_shared_cooldown(tmp_path,header):
    root = tmp_path/"ip"
    a,b = [PollFence(root,scope="FIXTURE:NAT",verified_weight=8) for _ in range(2)]
    assert a.claim("1"*64,10,2)[0]=="CLAIMED"
    assert b.claim("2"*64,10,2)[0]=="EXCLUSIVE_OWNER_BUSY"
    result = a.complete("1"*64,11,429,retry_after=header)
    assert result["retry_at"]>=60_011
    assert b.claim("2"*64,12,2)[0]=="COOLDOWN_OR_BAN"
    assert b.claim("2"*64,result["retry_at"],2)[0]=="CLAIMED"
    assert b.complete("2"*64,result["retry_at"],418)["ban"]
    assert a.claim("3"*64,200_000,2)[0]=="COOLDOWN_OR_BAN"


def test_actual_process_lost_ack_and_bounded_retry(tmp_path):
    root = tmp_path/"ip"
    child = """import os,sys
from aql.archive.source_poll import PollFence
p=PollFence(sys.argv[1],scope='FIXTURE:NAT',verified_weight=8)
assert p.claim('1'*64,100,2)[0]=='CLAIMED'
os._exit(73)
"""
    proc = subprocess.run([sys.executable,"-B","-c",child,str(root)],capture_output=True,timeout=30)
    assert proc.returncode==73,proc.stderr.decode()
    fence = PollFence(root,scope="FIXTURE:NAT",verified_weight=8)
    assert fence.claim("1"*64,101,2)[0]=="PENDING_ACK"
    assert fence.claim("2"*64,101,2)[0]=="EXCLUSIVE_OWNER_BUSY"
    with pytest.raises(ValueError,match="LOST_ACK_NOT_DUE"):
        fence.complete("1"*64,102,0,lost=True)
    result = fence.complete("1"*64,5100,0,lost=True)
    assert fence.claim("1"*64,5101,2)==("REPLAY",result)
    assert fence.health(5102)["used_weight"]==2
    with pytest.raises(ValueError,match="POLL_CLOCK_REGRESSION"):
        fence.health(5101)


def test_two_workers_and_continuous_core_discoverer_soak(discoverer,tmp_path):
    p = plan_for(discoverer)
    root = tmp_path/"ip"
    a,b = [PollFence(root,scope="FIXTURE:NAT",verified_weight=8) for _ in range(2)]
    def worker(index):
        owner = (a,b)[index]
        for i in range(40):
            token = digest([index,i])
            if owner.claim(token,200,2)[0]=="CLAIMED":
                owner.complete(token,200,200,result_pin=digest(i))
    with ThreadPoolExecutor(2) as pool:
        list(pool.map(worker,(0,1)))
    assert a.health(200)["used_weight"] == 4
    assert a.health(200)["queue_depth"] == 0
    slots = tuple(range(200,1400,100))
    repository = view(inventory(slots),access=2000)
    loop = discoverer.Loop(tmp_path/"loop",p,p["sha256"])
    fence = PollFence(tmp_path/"read",scope="FIXTURE:CORE",verified_weight=100)
    for slot in slots:
        def read_core(at):
            status,payload = fence.read(digest(["snapshot",at]),at,1,
                                       lambda timeout:repository.snapshot(at,p,p["sha256"])[0])
            assert status=="ACK"
            assert payload["receipt"]["measurements"]["payload_bytes"] > 0
            snapshot = payload["value"]
            return snapshot,snapshot["sha256"]
        def context(query):
            response,_ = repository.context(query,query["sha256"])
            return response,response["sha256"]
        assert len(loop.poll(slot,read_core,context))==1
    assert len(loop.journal.attempt_events())==12 and fence.health(slots[-1])["states"]=={"ACK":12}
    def timeout(**_):
        raise TimeoutError("fixture outage")
    assert fence.read(digest("timeout"),1400,1,timeout)[0]=="UNKNOWN"


def test_pinned_scanner_monitor_and_lab_boundary(tmp_path):
    source, market = "FIXTURE:PRICE", {"venue":"BINANCE","symbol":"BTC"}
    rights = dict(source=source,state="VERIFIED",uses=["MONITOR_ONLY"],valid_from=0,expires_at=1_000_000)
    pin = digest(rights)
    record = dict(key="bar:0",version=1,prior=None,source=source,market=market,use="MONITOR_ONLY",
                  grade="TEST_ONLY",value=dict(open="100",high="101",low="99",close="100",volume="1"),
                  final=True,event_at=899_999,published_at=900_000,received_at=900_001,
                  committed_at=900_002,known_at=None,witness=None,rights=pin)
    args = dict(expected_keys=["bar:0"],rights_by_digest={pin:rights},source=source,market=market,
                cutoff=900_003,max_age_ms=10,use="MONITOR_ONLY")
    source_view = as_of_view([record],pins={("bar:0",1):digest(record)},**args)
    packet = scanner_monitor_view(source_view,source_view["digest"],opens=[0],step_ms=900_000)
    assert packet["status"]=="READY_FIXTURE" and packet["authority"]=="NONE"
    # Execute the exact function body without the full Scanner entry point's
    # unrelated policy/warehouse dependencies on unmerged B/C branches.
    from research_wp_r0.aql_factory_historical_rule_projection import _vectors, _expression
    raw = git("show",S+":tools/scanner_strategy_f/research_e2e_diagnostic.py")
    body = [node for node in ast.parse(raw).body
            if isinstance(node,ast.FunctionDef) and node.name=="_eval_strategy"]
    assert len(body)==1
    scanner = {"_vectors":_vectors,"_expression":_expression}
    exec(compile(ast.Module(body=body,type_ignores=[]),"pinned_scanner_kernel","exec"),scanner)
    from research_wp_r0.strategy_definition import StrategyDefinition
    signal = {"op":"indicator","name":"trend","field":"value","lag":0}
    definition = StrategyDefinition({
        "schema_version":"1","strategy_id":"monitor_fixture","strategy_version":"v1","scope":"RESEARCH_ONLY",
        "indicators":[{"name":"trend","indicator_id":"SMA_v1","version":"1","parameters":{"period":3},
                       "constraints":{"period":{"type":"int","min":2,"max":20}}}],
        "entry":{"op":"gt","left":signal,"right":{"op":"constant","value":100}},
        "exit":{"op":"lt","left":signal,"right":{"op":"constant","value":99}},
        "timing":{"decision":"CONFIRMED_CLOSE","entry_execution":"NEXT_ELIGIBLE_OPEN","ambiguity":"REJECT"},
        "risk":{"unit":"ENTRY_NOTIONAL","max_exposure":1,"max_leverage":1,
                "stop_fraction":.02,"target_fraction":.04,"entry_ttl_bars":2,"holding_bars":10}})
    assert scanner["_eval_strategy"](definition,packet["bars"]) == [[899_999,"UNKNOWN"]]
    absent = as_of_view([],pins={},**args)
    assert scanner_monitor_view(absent,absent["digest"],opens=[0],step_ms=900_000)["bars"] == []
    from research_wp_r0.aql_factory_h_scientific_lab_v1 import evaluate_immutable_ledger
    with pytest.raises(ValueError):
        evaluate_immutable_ledger(packet)
