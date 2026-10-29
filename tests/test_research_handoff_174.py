"""Only new data-only seam. Public fixtures are synthetic, never private bytes."""
from dataclasses import asdict,replace
from pathlib import Path
import copy
import sys

import pytest

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/"src")]
from research_wp_r0.realdev_research_data import (
    accept_prefix,ResearchPermit,ResearchOnlyDenied,CONSUMER,SCOPE,OWNER,digest,
)
from aql.historical.research_handoff import (
    ResearchCapability,validate_research_capability,handoff_local_pair,replay_handoff,
)
from aql.historical.realdev_integration import (
    RuntimePin,IntegrationCapability,IntegrationDenied,EXPERIMENT,RAW_SHA,RECEIPT_SHA,
    START,END,SCHEMA,FACTORY_SHA,FACTORY_COMPATIBILITY,OWNER_SCOPE,
)


def fixture():
    rows=[[START+i*60000,START+(i+1)*60000-1,10.,12.,9.,11.,2.] for i in range(30)]
    runtime=dict(host="synthetic",account="fixture",python="fixture-python",python_version="3.12",
                 checkout="fixture",head="a"*40)
    m=dict(schema="core-factory-research-prefix-1",experiment_id=EXPERIMENT,consumer_id=CONSUMER,
        source_kind="SYNTHETIC_CONTRACT_FIXTURE",runtime=runtime,code_sha=runtime["head"],
        base_core_sha="22d03f4d3434fbce149c4d66349b33149789613a",factory_sha=FACTORY_SHA,
        mapping_schema=SCHEMA,compatibility_profile=FACTORY_COMPATIBILITY,symbol="BTCUSDT",interval_ms=60000,
        timezone="UTC",source_start_ms=START,source_end_ms_exclusive=START+30*60000,
        prefix_start_ms=START,prefix_end_ms_exclusive=START+24*60000,decision_cutoff_ms=START+24*60000,
        warmup_input_count=22,raw_archive_sha256="b"*64,raw_archive_size=100,
        issued_receipt_sha256="c"*64,issued_receipt_size=100,retained_archive_version=0,
        inspection_report_sha256="d"*64,full_normalized7_sha256=digest(rows),
        source_id="synthetic:contract-only",issued_receipt_id="synthetic:not-original")
    expected=dict(code_sha=m["code_sha"],runtime_sha256=digest(runtime),raw_archive_sha256="b"*64,
        issued_receipt_sha256="c"*64,inspection_report_sha256="d"*64,
        full_normalized7_sha256=digest(rows),prefix_normalized7_sha256=digest(rows[:24]))
    permit=ResearchPermit(EXPERIMENT,OWNER,CONSUMER,m["code_sha"],digest(runtime))
    return rows[:24],m,expected,permit


def accept(f,**kwargs):
    rows,m,expected,permit=f
    return accept_prefix(rows,metadata=m,expected=expected,permit=permit,request=SCOPE,**kwargs)


def core_cap():
    runtime=RuntimePin("fixture","fixture","fixture","3.12","fixture","a"*40)
    inspection=IntegrationCapability(EXPERIMENT,"DEV_INTEGRATION_ONLY",OWNER_SCOPE,runtime,
        RAW_SHA,RECEIPT_SHA,SCHEMA,FACTORY_SHA,FACTORY_COMPATIBILITY,START,END,END,22)
    return ResearchCapability(EXPERIMENT,SCOPE,OWNER,CONSUMER,runtime,inspection,
                              START,START+24*60000,START+24*60000,22)


def test_synthetic_positive_deterministic_bounded_immutable_rows():
    f=fixture();before=copy.deepcopy(f)
    a,b=accept(f),accept(copy.deepcopy(f))
    assert a.payload==b.payload and a.receipt_sha256==b.receipt_sha256 and f==before
    assert len(a.rows)==24 and a.rows[-1][1]<f[1]["decision_cutoff_ms"]
    assert a.spec["actual_fill"] is False and a.spec["factory_execution_eligible"] is False
    assert a.spec["DEV_ONLY"] and a.spec["NOT_PIT"] and a.spec["NOT_EMPIRICALLY_VALIDATED"]
    assert all(v=="NOT_CONFIGURED" for v in a.spec["execution_policy"].values())
    assert not any(k in a.spec for k in ("signals","orders","fills","cash","pnl","positions"))
    detached=a.request(SCOPE);detached["normalized7"][0][2]=99.
    assert a.rows[0][2]==10.
    c=core_cap();validate_research_capability(c,c.runtime,SCOPE)


@pytest.mark.parametrize("scope_name",[None,"EXECUTE","STRATEGY","ORDER","FILL","PNL","PIT","OOS",
                                      "PAPER","LIVE","GUARDIAN","REAL_SOURCE"])
def test_independent_core_and_factory_execution_refusal(scope_name):
    rows,m,e,p=fixture()
    with pytest.raises(ResearchOnlyDenied,match="FACTORY_DEFAULT_DENY"):
        accept_prefix(rows,metadata=m,expected=e,permit=p,request=scope_name)
    with pytest.raises(ResearchOnlyDenied,match="FACTORY_DEFAULT_DENY"):
        accept(fixture()).request(scope_name)
    with pytest.raises(ResearchOnlyDenied,match="CORE_DEFAULT_DENY"):
        handoff_local_pair("missing","missing",checkout=ROOT,capability=core_cap(),request=scope_name)


@pytest.mark.parametrize("field,value",[("schema","old"),("mapping_schema","old"),
    ("compatibility_profile","unknown"),("symbol","ETHUSDT"),("interval_ms",300000),
    ("timezone","LOCAL"),("code_sha","b"*40),("factory_sha","old"),
    ("raw_archive_sha256","f"*64),("issued_receipt_sha256","f"*64),
    ("inspection_report_sha256","f"*64),("decision_cutoff_ms",START),
    ("warmup_input_count",21),("warmup_input_count",True),("prefix_start_ms",START+60000),
    ("source_id",None),("issued_receipt_id",None)])
def test_wrong_source_receipt_schema_code_profile_or_cutoff(field,value):
    f=fixture();f[1][field]=value
    with pytest.raises(ValueError):accept(f)


@pytest.mark.parametrize("field",["host","account","python","python_version","checkout","head"])
def test_wrong_core_runtime(field):
    c=core_cap()
    with pytest.raises(ResearchOnlyDenied,match="STALE_RUNTIME_HEAD"):
        validate_research_capability(c,replace(c.runtime,**{field:"changed"}),SCOPE)


def test_factory_runtime_and_unsigned_claims_refused():
    f=fixture();f[1]["runtime"]["host"]="changed"
    with pytest.raises(ResearchOnlyDenied,match="RUNTIME"):accept(f)
    for field in ("real_pit_accepted","empirical_eligible","modeled_quote","available_ms"):
        f=fixture();f[1][field]=True
        with pytest.raises(ResearchOnlyDenied,match="METADATA_SHAPE"):accept(f)
    f=fixture()
    with pytest.raises(ResearchOnlyDenied,match="EXPLICIT_PERMIT"):
        accept_prefix(f[0],metadata=f[1],expected=f[2],permit={"approved":True},request=SCOPE)


@pytest.mark.parametrize("kind",["future_tail","gap","duplicate","order","nonfinite","ohlc","close"])
def test_future_data_or_bad_normalized_prefix_rejected(kind):
    rows,m,e,p=fixture()
    if kind=="future_tail":rows.append([START+24*60000,START+25*60000-1,10.,12.,9.,11.,2.])
    elif kind=="gap":rows.pop(10)
    elif kind=="duplicate":rows[10]=rows[9][:]
    elif kind=="order":rows.reverse()
    elif kind=="nonfinite":rows[10][2]=float("nan")
    elif kind=="ohlc":rows[10][3]=1.
    else:rows[10][1]+=1
    with pytest.raises(ValueError):accept((rows,m,e,p))


def test_missing_inspection_and_rehashed_row_digest_do_not_pass():
    f=fixture();del f[1]["inspection_report_sha256"]
    with pytest.raises(ValueError):accept(f)
    f=fixture();f[0][0][2]=10.5
    with pytest.raises(ResearchOnlyDenied,match="ROWS_COMMITMENT"):accept(f)
    c=core_cap()
    with pytest.raises(ResearchOnlyDenied,match="INSPECTION_REQUIRED"):
        validate_research_capability(replace(c,input_inspection={"report":"forged"}),c.runtime,SCOPE)


@pytest.mark.parametrize("kind",["missing","tampered_zip","tampered_receipt"])
def test_forged_metadata_cannot_replace_fresh_original_reads(monkeypatch,tmp_path,kind):
    import aql.historical.research_handoff as h
    c=core_cap()
    # Adversarial stale metadata check: even if prior inspection were forged,
    # the NEW row-supplying snapshot still requires the original immutable pins.
    monkeypatch.setattr(h,"observe_runtime",lambda _:c.runtime)
    monkeypatch.setattr(h.subprocess,"run",lambda *a,**k:None)
    monkeypatch.setattr(h,"inspect_local_pair",lambda *a,**k:object())
    raw,issued=tmp_path/"source.zip",tmp_path/"issued.json"
    if kind!="missing":raw.write_bytes(b"not-original")
    issued.write_bytes(b"not-original-receipt")
    if kind=="tampered_receipt":
        # Isolate receipt boundary with a synthetic first-read stub, NOT an
        # actual original-file claim. The second read must still refuse bytes.
        original=h.read_pinned_file
        def read(path,size,expected):
            if path==raw:return b"fixture",{}
            return original(path,size,expected)
        monkeypatch.setattr(h,"read_pinned_file",read)
    with pytest.raises(IntegrationDenied):
        h.handoff_local_pair(raw,issued,checkout=ROOT,capability=c,request=SCOPE)


def test_report_alone_or_bad_replay_commitment_never_supplies_rows():
    with pytest.raises(TypeError):
        handoff_local_pair("missing","missing",checkout=ROOT,report={"status":"PASS"})
    with pytest.raises(ResearchOnlyDenied,match="HANDOFF_COMMITMENT"):
        replay_handoff(accept(fixture()),expected_digest="f"*64)
