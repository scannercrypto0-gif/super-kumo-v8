"""Targeted independent falsifiers for Council #051-#053, no replay rewrite."""
from dataclasses import replace
import pytest
from research_wp_r0.indicator_library import (
    IndicatorLibrary, IndicatorManifest, IndicatorResult, RSIIndicator, EMAIndicator,
)

def test_flat_rsi_semantic_version_separates_historical_v1():
    v1=IndicatorLibrary().get("RSI_v1",period=3)
    v2=IndicatorLibrary().get("RSI_v2",period=3)
    flat=[100.0]*9
    rising=[float(i+1) for i in range(9)]
    falling=[float(100-i) for i in range(9)]
    assert v1._compute_values(flat,[])[-1]==100.0
    assert v2._compute_values(flat,[])[-1]==50.0
    assert v2._compute_values(rising,[])[-1]==100.0
    assert v2._compute_values(falling,[])[-1]==0.0
    assert v1.indicator_id!=v2.indicator_id
    assert v1.version!=v2.version

@pytest.mark.parametrize("s",[float("nan"),float("inf"),float("-inf"),0,-1,9,True])
def test_ema_smoothing_must_produce_convex_weight(s):
    with pytest.raises((ValueError,TypeError)):
        EMAIndicator(period=2,smoothing=s)

@pytest.mark.parametrize("s",[0.01,3])
def test_ema_boundary_alpha_is_valid(s):
    ema=EMAIndicator(period=2,smoothing=s)
    assert 0 < ema.smoothing/(ema.period+1) <= 1

def test_manifest_rejects_identity_and_value_tampering():
    r=IndicatorResult.create("RSI_v1","1","fixture",1,"a"*64,123,200,50.0,
                             (("period",3),),3,False)
    m=IndicatorManifest.create("RSI_v1","fixture",1,"a"*64,200,
                               (("period",3),),3,[r])
    assert m.verify([r])
    assert not replace(m,dataset_id="other").verify([r])
    assert not replace(m,decision_cutoff_ms=201).verify([r])
    assert not replace(m,parameter_set=(("period",4),)).verify([r])
    assert not m.verify([replace(r,value=100.0)])
    forged=IndicatorResult.create("RSI_v1","1","elsewhere",1,"a"*64,123,200,50.0,
                                  (("period",3),),3,False)
    m2=replace(m,computation_hash=IndicatorManifest._hash_results([forged]))
    assert not m2.verify([forged])
