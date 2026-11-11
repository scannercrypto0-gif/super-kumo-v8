"""M18 actual opt-in Factory exam admission barrier with R0 fixture."""
import copy
import pytest
from research_wp_r0.factory_exam_example import fixture
from research_wp_r0.factory_exam import freeze_protocol, run_route
from research_wp_r0.guarded_factory_exam import freeze_manifest_guarded


def vector():
    return dict(indicator_id="MACD_v2",version=2,parameter_set=[["fast",8],["slow",21],["signal",9]],
                dataset_id="SYNTHETIC",dataset_version=1,dataset_manifest_hash="a"*64,
                decision_cutoff_ms=1000,start_ms=1,end_ms=1000,warmup_policy=28,
                input_bar_hash="b"*64,result_hashes=["c"*64],output_fields=["macd","signal","hist"])

def test_equal_opt_in_manifests_use_existing_synthetic_r0_path():
    dna,events,config=fixture()
    manifest,identities=freeze_manifest_guarded(dna,events,
        scanner_vectors={"trend":vector()},decision_vectors={"trend":copy.deepcopy(vector())})
    assert "trend" in identities
    protocol=freeze_protocol(manifest,expected_manifest_digest=manifest.digest,config=config)
    results=run_route(manifest,protocol,expected_manifest_digest=manifest.digest,
                      expected_protocol_digest=protocol.digest,arm="ALWAYS").spec
    assert len(results["outcomes"])==len(events)
    assert any(o["status"]=="EXECUTED" for o in results["outcomes"])

def test_mismatched_window_prevents_scanner_decision_run():
    dna,events,_=fixture()
    other=vector();other["start_ms"]=20
    with pytest.raises(ValueError,match="M18"):
        freeze_manifest_guarded(dna,events,scanner_vectors={"trend":vector()},
                                decision_vectors={"trend":other})

def test_missing_comparison_side_refused():
    dna,events,_=fixture()
    with pytest.raises(ValueError,match="M18"):
        freeze_manifest_guarded(dna,events,scanner_vectors={"trend":vector()},
                                decision_vectors={})
