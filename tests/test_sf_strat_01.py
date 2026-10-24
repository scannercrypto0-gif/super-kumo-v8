import dataclasses
import json
import pathlib
import sys
from unittest.mock import Mock, patch
import pytest
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from research_wp_r0.strategy_definition import (
    StrategyDefinition, EvaluationBinding, AttemptRecorder, canonical, digest,
    bind_evaluation, candidate_grid, load_json)
from research_wp_r0.historical_library import HistoricalDataError
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from test_sf_ind_01 import _bars, _lib_with as _base_lib, BASE_MS, IMS


def spec():
    return {"schema_version":"1","strategy_id":"example","strategy_version":"v1","scope":"RESEARCH_ONLY",
            "indicators":[{"name":"trend","indicator_id":"SMA_v1","version":"1",
                           "parameters":{"period":3},"constraints":{"period":{"type":"int","min":2,"max":20}}}],
            "entry":{"op":"gt","left":{"op":"indicator","name":"trend","field":"value","lag":0},
                     "right":{"op":"constant","value":100}},
            "exit":{"op":"lt","left":{"op":"indicator","name":"trend","field":"value","lag":1},
                    "right":{"op":"constant","value":99}},
            "timing":{"decision":"CONFIRMED_CLOSE","entry_execution":"NEXT_ELIGIBLE_OPEN","ambiguity":"REJECT"},
            "risk":{"unit":"ENTRY_NOTIONAL","max_exposure":1,"max_leverage":1,
                    "stop_fraction":.02,"target_fraction":.04,"entry_ttl_bars":2,"holding_bars":10}}


def definition():
    return StrategyDefinition(spec())


def binding(d=None, bars=None, cutoff=None, registry=None):
    bars = _bars(10, step=1) if bars is None else bars
    _, accessor = _lib_with(bars)
    return bind_evaluation(d or definition(), accessor, "BTC1M", 1, BASE_MS,
                           BASE_MS+9*IMS, cutoff or BASE_MS+10*IMS, registry=registry)


def test_roundtrip_and_immutable():
    d = definition()
    assert StrategyDefinition.from_json(d.to_json()) == d
    assert StrategyDefinition.from_dict(d.to_dict()).digest == d.digest
    v=d.spec;v["risk"]["stop_fraction"]=.8
    assert d.spec["risk"]["stop_fraction"]==.02
    with pytest.raises(dataclasses.FrozenInstanceError):
        d.payload=b"bad"


@pytest.mark.parametrize("path,value", [
    ("schema_version","2"),("scope","LIVE"),("strategy_id","x()"),("extra",1),
    ("strategy_version",True),("indicators",[]),("entry",{"op":"eval","code":"x()"}),
    ("entry",{"op":"constant","value":1}),("entry",{"op":"not","arg":{"op":"constant","value":1}}),
])
def test_invalid_top_level(path,value):
    v=spec();v[path]=value
    with pytest.raises(ValueError):StrategyDefinition(v)


@pytest.mark.parametrize("value",[True,2.0,0,-2,float("nan"),float("inf"),"3",None])
def test_strict_period(value):
    v=spec();v["indicators"][0]["parameters"]["period"]=value
    with pytest.raises(ValueError):StrategyDefinition(v)


@pytest.mark.parametrize("change",["unknown","version","field","future_lag","extra_param","duplicate","constraint"])
def test_invalid_references(change):
    v=spec();r=v["indicators"][0]
    if change=="unknown":r["indicator_id"]="FUNDING_v1"
    if change=="version":r["version"]="2"
    if change=="field":v["entry"]["left"]["field"]="histogram"
    if change=="future_lag":v["entry"]["left"]["lag"]=-1
    if change=="extra_param":r["parameters"]["evil"]=1
    if change=="duplicate":v["indicators"].append(dict(r))
    if change=="constraint":r["constraints"]["period"]["max"]=2
    with pytest.raises(ValueError):StrategyDefinition(v)


@pytest.mark.parametrize("key,value",[("stop_fraction",0),("target_fraction",float("nan")),
    ("max_leverage",2),("max_exposure",True),("entry_ttl_bars",False),("holding_bars",0),("unit","ACCOUNT_EQUITY")])
def test_risk_rejected(key,value):
    v=spec();v["risk"][key]=value
    with pytest.raises(ValueError):StrategyDefinition(v)


def test_timing_and_ast_bounds():
    v=spec();v["timing"]["decision"]="INTRABAR"
    with pytest.raises(ValueError):StrategyDefinition(v)
    v=spec()
    for _ in range(10):v["entry"]={"op":"not","arg":v["entry"]}
    with pytest.raises(ValueError):StrategyDefinition(v)


@pytest.mark.parametrize("raw",['{"x":1,"x":2}','{"x":NaN}','{"x":Infinity}'])
def test_strict_json(raw):
    with pytest.raises(ValueError):load_json(raw)


def test_numeric_canonicalization_and_golden():
    assert canonical({"b":1.0,"a":-0.0})==b'{"a":0,"b":1}'
    assert digest({"b":1.0,"a":-0.0})=="f4c1d8bd90d7ccd720aa5a69a67185fb9caf4f35926a4eacf53a86d0e70bdf88"
    with pytest.raises(ValueError):canonical({"large":2**54})
    with pytest.raises(ValueError):canonical({"x":object()})
    with pytest.raises(ValueError):canonical({"x":float("nan")})


def test_definition_tamper_and_version():
    d=definition();v=d.to_dict();v["definition"]["risk"]["stop_fraction"]=.1
    with pytest.raises(ValueError):StrategyDefinition.from_dict(v)
    v=spec();v["strategy_version"]="v2"
    assert StrategyDefinition(v).digest!=d.digest


def test_grid_retains_all_and_bounds():
    items=candidate_grid(definition(),{"trend.period":[2,3,4]})
    assert len(items)==3 and len({x.digest for x in items})==3
    for axes in ({"trend.period":[3,3]}, {"trend.period":[True]}, {"bad.x":[2]}):
        with pytest.raises(ValueError):candidate_grid(definition(),axes)
    with pytest.raises(ValueError):candidate_grid(definition(),{"trend.period":[2,3]},maximum=1)


def test_pit_binding_roundtrip_tamper_and_cutoff():
    d=definition();b=binding(d)
    assert EvaluationBinding.from_dict(b.to_dict(),expected_digest=b.digest)==b
    changed=b.to_dict();changed["binding"]["decision_cutoff_ms"]+=1
    with pytest.raises(ValueError):EvaluationBinding.from_dict(changed,expected_digest=b.digest)
    later=binding(d,cutoff=BASE_MS+11*IMS)
    assert later.digest!=b.digest and d.digest==definition().digest


def test_future_gap_warmup_retrospective_fail_closed():
    with pytest.raises(HistoricalDataError):binding(cutoff=BASE_MS+9*IMS)
    bars=_bars(10);bars.pop(5)
    with pytest.raises(HistoricalDataError):binding(bars=bars)
    v=spec();v["indicators"][0]["parameters"]["period"]=20
    with pytest.raises(ValueError):binding(StrategyDefinition(v))
    from research_wp_r0.historical_library import DataAvailabilityKind
    bars=[dataclasses.replace(b,availability_kind=DataAvailabilityKind.RETROSPECTIVE) for b in _bars(10)]
    with pytest.raises(HistoricalDataError):binding(bars=bars)


def test_manifest_mismatch_detected():
    from research_wp_r0.indicator_library import IndicatorLibrary
    class Registry(IndicatorLibrary):
        def get(self,*args,**kwargs):
            ind=super().get(*args,**kwargs);compute=ind.compute
            def bad(*a,**k):
                rows,manifest=compute(*a,**k)
                return rows,dataclasses.replace(manifest,decision_cutoff_ms=1)
            ind.compute=bad
            return ind
    with pytest.raises(ValueError):binding(registry=Registry())


def test_attempt_accounting_and_sink_failure():
    sink=Mock();recorder=AttemptRecorder(sink)
    with pytest.raises(ValueError):recorder.prepare('{"definition":{}}',"family","bad")
    assert sink.record_attempt.call_args.args[0]["state"]=="INVALID"
    pending,d=recorder.prepare(definition().to_json(),"family","candidate")
    assert sink.record_attempt.call_args.args[0]["state"]=="PENDING"
    b=binding(d)
    for state in ("FAILED","ABANDONED"):
        event=recorder.finish(pending,state)
        assert event["candidate_id"]=="candidate" and event["state"]==state
    event=recorder.finish(pending,"COMPLETE",binding=b,result_digest="a"*64)
    assert event["strategy_digest"]==d.digest and event["binding_digest"]==b.digest
    with pytest.raises(ValueError):recorder.finish(pending,"COMPLETE",result_digest="a"*64)
    sink.record_attempt.side_effect=OSError("unavailable")
    with pytest.raises(OSError):recorder.prepare(d.to_json(),"family","candidate")


def test_actual_dependency_guard():
    from research_wp_r0._dep_guard import check_file
    root=pathlib.Path(__file__).resolve().parents[1]
    assert check_file(root/"research_wp_r0/strategy_definition.py")==[]


def _lib_with(bars):
    # Fixture custody creation time is explicit: real manifests must not be rewritten.
    with patch("research_wp_r0.historical_library.time.time", return_value=1700000000):
        return _base_lib(bars)

def test_fixture_golden_definition_and_binding():
    assert definition().digest=="024283f5e191a49199cf2e65aada9f87113c076d6190653a57fbb1b5c739ef86"
    assert binding().digest=="8a17485390f47402dfca032ce99265bb8d0738d5cd26370a252a2bb175f71fdf"


def test_accessor_required_and_input_bounds():
    with pytest.raises(ValueError,match="CustodyAccessor"):
        bind_evaluation(definition(),object(),"x",1,0,0,1)
    with pytest.raises(ValueError):load_json(" " * 100001)
    with pytest.raises(ValueError):canonical({"x":1e100})


def test_example_matches_live_schema():
    example=json.loads((pathlib.Path(__file__).parents[1]/"examples/strategy_definition_v1.json").read_text(encoding="utf-8"))
    assert StrategyDefinition.from_dict(example)==definition()


def test_ema_explicit_parameters_and_boolean_nodes():
    v=spec()
    r=v["indicators"][0];r["indicator_id"]="EMA_v1"
    r["parameters"]["smoothing"]=2.0
    r["constraints"]["smoothing"]={"type":"number","min":.1,"max":2.0}
    v["entry"]={"op":"all","args":[v["entry"],{"op":"not","arg":v["exit"]}]}
    d=StrategyDefinition(v)
    assert binding(d)
    v["entry"]["args"][0]["left"]["name"]=[]
    with pytest.raises(ValueError):StrategyDefinition(v)

def test_extreme_numeric_invalid_attempt_is_retained():
    value=spec();value["risk"]["stop_fraction"]=10**500
    sink=Mock()
    raw=json.dumps({"definition":value,"digest":"0"*64})
    with pytest.raises(ValueError):
        AttemptRecorder(sink).prepare(raw,"family","huge")
    assert sink.record_attempt.call_args.args[0]["state"]=="INVALID"


@pytest.mark.parametrize("raw", ['{"x":1e9999}', '{"x":1e-9999}', '{"x":-1e-9999}'])
def test_json_float_extremes_fail_closed(raw):
    with pytest.raises(ValueError):load_json(raw)


def test_unexpected_registry_failure_is_recorded_and_propagated():
    class BrokenRegistry:
        def get(self,*args,**kwargs):raise RuntimeError("provider unavailable")
    sink=Mock()
    with pytest.raises(RuntimeError,match="provider unavailable"):
        AttemptRecorder(sink).prepare(definition().to_json(),"family","candidate",registry=BrokenRegistry())
    event=sink.record_attempt.call_args.args[0]
    assert event["state"]=="FAILED" and event["candidate_id"]=="candidate"
    assert event["input_digest"] and event["error_type"]=="RuntimeError"
    sink.record_attempt.side_effect=OSError("ledger unavailable")
    with pytest.raises(OSError,match="ledger unavailable"):
        AttemptRecorder(sink).prepare(definition().to_json(),"family","candidate",registry=BrokenRegistry())


def test_wrong_result_warmup_rejected_even_with_consistent_hashes():
    from research_wp_r0.indicator_library import IndicatorLibrary,IndicatorResult,IndicatorManifest
    class Registry(IndicatorLibrary):
        def get(self,*args,**kwargs):
            ind=super().get(*args,**kwargs);compute=ind.compute
            def bad(*a,**k):
                rows,manifest=compute(*a,**k)
                fields=rows[-1].to_dict();fields.pop("provenance_hash")
                fields["warmup_bars_consumed"]+=1
                rows[-1]=IndicatorResult.create(**fields)
                manifest=dataclasses.replace(manifest,computation_hash=IndicatorManifest._hash_results(rows))
                return rows,manifest
            ind.compute=bad
            return ind
    with pytest.raises(ValueError,match="warmup"):
        binding(registry=Registry())


def test_vector_contract_cannot_accept_scalar_result():
    from research_wp_r0.indicator_library import IndicatorLibrary
    class Registry(IndicatorLibrary):
        def get(self,*args,**kwargs):
            ind=super().get(*args,**kwargs)
            ind.output_fields=("first","second")
            return ind
    value=spec();value["entry"]["left"]["field"]="first";value["exit"]["left"]["field"]="second"
    with pytest.raises(ValueError,match="Typed output"):
        binding(StrategyDefinition(value,registry=Registry()),registry=Registry())
