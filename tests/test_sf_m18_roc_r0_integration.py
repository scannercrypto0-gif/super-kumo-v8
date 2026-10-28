"""Actual ROC_v2 -> calculated manifest -> StrategyDNA -> R0 synthetic proof."""
from copy import deepcopy
from research_wp_r0.historical_library import (
    HistoricalLibrary, CustodyAccessor, make_test_bar, validate_bars
)
from research_wp_r0.indicator_library_v2 import IndicatorRegistryV2
from research_wp_r0.strategy_dna_v2 import StrategyDNAV2, reference_digest
from research_wp_r0.strategy_dna_v2_example import example
from research_wp_r0.factory_exam import freeze_protocol, run_route, replay_route
from research_wp_r0.guarded_factory_exam import freeze_manifest_computed_guarded

def test_real_calculated_roc_value_flows_to_synthetic_r0():
    v1, old, _ = example()
    spec = deepcopy(old.spec)
    ref = dict(name="trend", indicator_id="ROC_v2", version="2",
               parameters={"period": 2},
               constraints={"period": {"type":"int", "min":2, "max":20}})
    spec["indicators"] = [ref]
    spec["strategy_version"] = "v2_roc_bound"
    def inp():
        return dict(reference="trend",field="roc",max_age_ms=60000)
    spec["scanner_profile"]["filters"] = [
        dict(rule_id="roc_positive",**inp(),operator="gt",value=0)]
    spec["scanner_profile"]["ranking"] = [dict(**inp(),direction="DESC")]
    def term(direction):
        return dict(term_id="roc_score",**inp(),weight=1,
                    lower=0,upper=2,direction=direction)
    spec["decision_profile"]["entry"] = dict(terms=[term("HIGH")],
                                              threshold=.5,mandatory=[])
    spec["decision_profile"]["exit"] = dict(terms=[term("LOW")],
                                             threshold=.8,mandatory=[])
    spec["monitoring_profile"]["features"] = [
        dict(feature_id="roc_observe",**inp())]
    dna = StrategyDNAV2(spec, v1_definition=v1)
    bars = [make_test_bar(i) for i in range(3)]
    good, meta = validate_bars(bars,"BTCUSDT","1m")
    library = HistoricalLibrary()
    library.register("ROC_TEST",good,meta)
    accessor = CustodyAccessor(library)
    cutoff = bars[-1].bar_close + 1
    indicator = IndicatorRegistryV2().get("ROC_v2",period=2)
    results,manifest = indicator.compute(
        accessor,"ROC_TEST",bars[0].bar_open,bars[-1].bar_open,cutoff,version=1)
    assert len(results)==1
    value = dict(results[-1].value)["roc"]
    assert 1 < value < 2  # percentage points, not fractional return
    observation = dict(
        indicator_digest=reference_digest(ref),source_kind="SYNTHETIC",
        source_id="generator",source_generation_id="fixture_v1",
        quality="VALID",is_final=True,
        as_of_ms=cutoff,observed_at_ms=cutoff,available_at_ms=cutoff,
        values={"roc":value})
    event=dict(event_id="ROC1",cutoff_ms=cutoff,symbol="AAA",venue="fixture",
               features={"trend":observation},
               quotes=[dict(at_ms=cutoff+1,available_at_ms=cutoff+1,price=100),
                       dict(at_ms=cutoff+101,available_at_ms=cutoff+101,price=101)],
               fill_fraction=1,regime=None,protection=None)
    proof=dict(results=results,manifest=manifest,
               as_of_ms=cutoff,observed_at_ms=cutoff,available_at_ms=cutoff)
    vectors={"trend":manifest.to_dict()}
    frozen,_=freeze_manifest_computed_guarded(
        dna,[event],computed_by_event={"ROC1":{"trend":proof}},
        scanner_vectors=vectors,decision_vectors=deepcopy(vectors),
        calculation_inputs={"ROC1":{"trend":dict(accessor=accessor,dataset_id="ROC_TEST",
            version=1,start_ms=bars[0].bar_open,end_ms=bars[-1].bar_open)}})
    assert frozen.spec["rows"][0]["decision"]["signal"]=="ENTRY_CONDITION_MET"
    config=dict(schema="factory-exam-protocol-1",seed=7,capital=1000,notional=100,
                fee_bps=0,spread_bps=0,slippage_bps=0,latency_ms=1,
                holding_ms=100,exit_policy="DNA_EXIT_OR_NATIVE_HORIZON_LONG",
                protection_required=False,regime_threshold=.5,regime_max_age_ms=100,
                trial_id="ROC_BOUND",registered_at_ms=0,parameter_count=0,overlay=None)
    protocol=freeze_protocol(frozen,expected_manifest_digest=frozen.digest,config=config)
    route=run_route(frozen,protocol,expected_manifest_digest=frozen.digest,
                    expected_protocol_digest=protocol.digest,arm="ALWAYS")
    assert route.spec["outcomes"][0]["status"]=="EXECUTED"
    assert any(x["kind"]=="SIMULATED_ENTRY" for x in route.spec["ledger"])
    assert any(x["kind"]=="SIMULATED_EXIT" for x in route.spec["ledger"])
    assert replay_route(frozen,protocol,route,arm="ALWAYS").digest==route.digest
