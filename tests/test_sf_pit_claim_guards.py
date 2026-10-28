"""Claim-bearing H1/H2 regression; synthetic dev paths remain separate."""
import pytest
from research_wp_r0.historical_library import (
    HistoricalLibrary, CustodyAccessor, make_test_bar, validate_bars,
    SourceType
)
from research_wp_r0.indicator_library_v2 import IndicatorRegistryV2
from research_wp_r0.strategy_definition import bind_evaluation
from research_wp_r0.strategy_dna_v2_example import example

def custody(*, receipt):
    bars=[]
    for i in range(3):
        temp=make_test_bar(i, source=SourceType.ARCHIVE)
        bars.append(make_test_bar(i,source=SourceType.ARCHIVE,
                                  ingest_time_ms=temp.bar_close+1 if receipt else None))
    good,meta=validate_bars(bars,"BTCUSDT","1m")
    lib=HistoricalLibrary()
    lib.register("PIT_TEST",good,meta)
    return lib,CustodyAccessor(lib),bars

def call_roc(accessor,bars,*,version):
    return IndicatorRegistryV2().get("ROC_v2",period=2).compute(
        accessor,"PIT_TEST",bars[0].bar_open,bars[-1].bar_open,
        bars[-1].bar_close+1,version=version)

def test_direct_indicator_rejects_confirmed_without_receipt():
    _,accessor,bars=custody(receipt=False)
    with pytest.raises(ValueError,match="receipt"):
        call_roc(accessor,bars,version=1)

def test_claim_bearing_version_must_be_explicit():
    _,accessor,bars=custody(receipt=True)
    with pytest.raises(ValueError,match="version must be pinned"):
        call_roc(accessor,bars,version=None)

def test_original_pinned_vintage_reproducible_corrected_unproven_fails_closed():
    lib,accessor,bars=custody(receipt=True)
    original,_=call_roc(accessor,bars,version=1)
    assert len(original)==1
    lib.correct("PIT_TEST",bars,"late synthetic correction rehearsal")
    repeat,_=call_roc(accessor,bars,version=1)
    assert [x.provenance_hash for x in original]==[x.provenance_hash for x in repeat]
    with pytest.raises(ValueError,match="corrected vintage"):
        call_roc(accessor,bars,version=2)

def test_direct_binding_also_rejects_missing_claim_receipt():
    _,accessor,bars=custody(receipt=False)
    v1,_,_=example()
    with pytest.raises(ValueError,match="receipt"):
        bind_evaluation(v1,accessor,"PIT_TEST",1,
                        bars[0].bar_open,bars[-1].bar_open,
                        bars[-1].bar_close+1)

def test_direct_binding_rejects_unproven_corrected_vintage():
    lib,accessor,bars=custody(receipt=True)
    lib.correct("PIT_TEST",bars,"unproven correction")
    v1,_,_=example()
    with pytest.raises(ValueError,match="corrected vintage"):
        bind_evaluation(v1,accessor,"PIT_TEST",2,
                        bars[0].bar_open,bars[-1].bar_open,
                        bars[-1].bar_close+1)
