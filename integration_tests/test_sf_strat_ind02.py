"""Explicit cross-PR integration. Not collected by the ordinary tests/ suite."""
import pathlib
import sys
from unittest.mock import Mock
import pytest
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]/"tests"))
from test_sf_strat_01 import spec,_lib_with,_bars,BASE_MS,IMS
from research_wp_r0.strategy_definition import StrategyDefinition,bind_evaluation,AttemptRecorder,EvaluationBinding
from research_wp_r0.indicator_library_v2 import IndicatorRegistryV2

CASES=[
    ("MACD_v2",{"fast":2,"slow":4,"signal":3},"histogram"),
    ("BBANDS_v2",{"period":3,"deviations":2.},"lower"),
    ("ADX_v2",{"period":3},"adx"),
    ("STOCH_v2",{"period":3,"smooth":2},"d"),
    ("ROC_v2",{"period":3},"roc"),
    ("OBV_v2",{},"obv")]


@pytest.mark.parametrize("name,params,field",CASES)
def test_v2_definition_binding_attempt_roundtrip(name,params,field):
    registry=IndicatorRegistryV2();value=spec()
    value["indicators"]=[{"name":"trend","indicator_id":name,"version":"2","parameters":params,
        "constraints":{k:{"type":"number" if k=="deviations" else "int","min":2,"max":20} for k in params}}]
    value["entry"]["left"]["field"]=field;value["exit"]["left"]["field"]=field
    d=StrategyDefinition(value,registry=registry)
    assert StrategyDefinition.from_json(d.to_json(),registry=registry)==d
    _,accessor=_lib_with(_bars(12,step=1))
    b=bind_evaluation(d,accessor,"BTC1M",1,BASE_MS,BASE_MS+11*IMS,BASE_MS+12*IMS,registry=registry)
    assert b.spec["indicators"][0]["manifest"]["indicator_id"]==name
    assert EvaluationBinding.from_dict(b.to_dict(),expected_digest=b.digest)==b
    altered=b.to_dict();altered["binding"]["indicators"][0]["parameters"]["unexpected"]=1
    with pytest.raises(ValueError):EvaluationBinding.from_dict(altered,expected_digest=b.digest)
    sink=Mock();recorder=AttemptRecorder(sink)
    attempt,_=recorder.prepare(d.to_json(),"family","candidate",registry=registry)
    event=recorder.finish(attempt,"COMPLETE",binding=b,result_digest="b"*64)
    assert event["strategy_digest"]==d.digest and event["binding_digest"]==b.digest
    value["entry"]["left"]["field"]="unknown_output"
    with pytest.raises(ValueError):StrategyDefinition(value,registry=registry)
