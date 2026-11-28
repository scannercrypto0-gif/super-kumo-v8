"""Frozen synthetic upstream read schema, integrity and denominator guards."""
from copy import deepcopy
import pytest
from aql.observation.contracts import digest
from aql.paper_sim.adapter import signals_from_prospective


def document():
    run=dict(strategy_id="fixture",strategy_version="v1",definition_sha256="a"*64,
             config_sha256="b"*64,evaluator_sha256="c"*64,strategy_fixture_sha256="d"*64,
             journal_instance="synthetic-journal",evidence_mode="SYNTHETIC_TESTED")
    rows=[]
    for i,state in enumerate(("ENTRY_SIGNAL","EXIT_SIGNAL","NO_SIGNAL","REJECTED","UNKNOWN")):
        parent=dict(key=f"BTCUSDT:15m:{i*900000}",close_ms=(i+1)*900000-1,
                    open_ms=i*900000,ingested_ms=(i+1)*900000,commit_ms=(i+1)*900000+1,
                    bar_checksum="a"*64,content_sha256="b"*64,g1_receipt_sha256="c"*64)
        decision=dict(run=run,parent=parent,cutoff_ms=(i+1)*900000+2,state=state,
                      reason=None,inputs=[],trading_authority="NONE")
        decision["opportunity_id"]=digest(decision) if state in {"ENTRY_SIGNAL","EXIT_SIGNAL"} else None
        rows.append(dict(decision=decision,decision_sha256=digest(decision),source_valid=True,
                         horizons=[{"value":"THIS_FUTURE_LABEL_MUST_NOT_BE_USED"}]))
    body=dict(schema="aql.g2.prospective-verified-read.v1",run=run,as_of_ms=6000000,
              rows=rows,visible_sha256=digest(rows),trading_authority="NONE")
    return {**body,"sha256":digest(body)}


def reseal(d):
    for row in d["rows"]:
        row["decision_sha256"]=digest(row["decision"])
    d["visible_sha256"]=digest(d["rows"])
    d["sha256"]=digest({k:v for k,v in d.items() if k!="sha256"})
    return d


def read(d,**changes):
    args=dict(expected_sha=d["sha256"],expected_run=deepcopy(d["run"]),as_of_ms=d["as_of_ms"])
    args.update(changes)
    return signals_from_prospective(d,**args)


def test_all_states_counted_only_entry_creates_sim_signal_no_horizon_leak():
    d=document();out=read(d)
    assert len(out["signals"])==1 and sum(out["census"].values())==5
    assert set(out["census"])=={"ENTRY_SIGNAL","EXIT_SIGNAL","NO_SIGNAL","REJECTED","UNKNOWN"}
    assert out["horizon_values_used"] is False and out["trading_authority"]=="NONE"
    d["rows"][0]["horizons"]=[{"value":"DIFFERENT_FUTURE_OUTCOME"}]
    reseal(d)
    assert read(d)["signals"]==out["signals"]


def test_expected_run_and_independently_retained_digest_are_mandatory():
    d=document()
    with pytest.raises(ValueError):read(d,expected_sha="f"*64)
    bad=deepcopy(d["run"]);bad["config_sha256"]="e"*64
    with pytest.raises(ValueError):read(d,expected_run=bad)
    d["rows"][0]["decision"]["state"]="NO_SIGNAL"
    with pytest.raises(ValueError):read(d)


@pytest.mark.parametrize("change",["source","live","future","row_sha","duplicate","opportunity","authority"])
def test_negative_source_and_identity_guards(change):
    d=document()
    if change=="source":d["rows"][0]["source_valid"]=False
    elif change=="live":d["run"]["evidence_mode"]="PUBLIC_WS_OBSERVATION"
    elif change=="future":d["rows"][0]["decision"]["cutoff_ms"]=999999999
    elif change=="row_sha":d["rows"][0]["decision"]["run"]={**d["run"],"strategy_version":"v2"}
    elif change=="duplicate":d["rows"].append(deepcopy(d["rows"][0]))
    elif change=="opportunity":d["rows"][0]["decision"]["opportunity_id"]="f"*64
    elif change=="authority":d["trading_authority"]="PAPER"
    reseal(d)
    with pytest.raises(ValueError):read(d)
