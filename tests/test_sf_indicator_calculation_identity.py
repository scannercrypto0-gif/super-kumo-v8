"""M18 negative scientific comparability: window/seed are identity."""
import copy
import pytest
from research_wp_r0.indicator_calculation_identity import require_same_calculation


def sample():
    return dict(indicator_id="MACD_v2",version=2,parameter_set=[["fast",8],["slow",21],["signal",9]],
                dataset_id="synthetic",dataset_version=1,dataset_manifest_hash="a"*64,
                decision_cutoff_ms=120, start_ms=0,end_ms=120,warmup_policy=28,
                input_bar_hash="b"*64,result_hashes=["c"*64],output_fields=["macd","signal","hist"])

def test_same_manifest_accepted_only_at_identity_level():
    a=sample()
    assert require_same_calculation(a,copy.deepcopy(a))

@pytest.mark.parametrize("field,new",[
    ("start_ms",20),("input_bar_hash","d"*64),("warmup_policy",29),
    ("result_hashes",["e"*64]),("decision_cutoff_ms",121)])
def test_changes_block_cross_consumer_comparison(field,new):
    a=sample();b=copy.deepcopy(a);b[field]=new
    with pytest.raises(ValueError,match="M18"):
        require_same_calculation(a,b)

def test_missing_manifest_blocks():
    with pytest.raises(ValueError):
        require_same_calculation({"indicator_id":"MACD_v2"},sample())
