"""B2 falsifiers for three strategy families across ex ante gate scenarios."""
from research_wp_r0.factory_b2_counterfactual import (
    FAMILIES,SCENARIOS,run_case,run_suite,
)

def test_all_preregistered_cases_have_matched_denominators_and_receipts():
    report=run_suite()
    assert len(report["cases"])==9
    assert report["no_alpha_promotion"] is True
    assert report["oos"]=="NOT_ACCESSED"
    assert report["order_io"]=="DISABLED"
    assert len(report["registered_design_digest"])==64
    for c in report["cases"]:
        assert c["scheduled"]==18
        assert c["monitoring_count"]==18
        assert c["comparison"]["left"]["scheduled"]==18
        assert c["comparison"]["right"]["scheduled"]==18
        assert c["comparison"]["left"]["unknown"]==0
        assert c["comparison"]["right"]["unknown"]==0
        assert c["comparison"]["comparison_kind"]=="MATCHED_ASSUMPTIONS"
        assert c["comparison"]["conditional_selection_sensitive"] is True
        assert c["replay"]=="EXACT_BOTH"
        assert len(c["opportunity_counterfactuals"])==18
        assert {x["event_id"] for x in c["opportunity_counterfactuals"]}=={
            "B2_%02d_%s"%(i,s) for i in range(6) for s in ("AAA","BBB","CCC")}
        assert all(x["paired_net_delta"] is not None for x in c["opportunity_counterfactuals"])

def test_gate_can_help_hurt_or_be_neutral_without_optimization():
    for family in FAMILIES:
        helps=run_case(family,"GATE_HELPS")
        hurts=run_case(family,"GATE_HURTS")
        neutral=run_case(family,"GATE_NEUTRAL")
        def net(case,arm):
            return case["comparison"][arm]["portfolio"]["net_quote"]
        assert net(helps,"right")>net(helps,"left")
        assert net(hurts,"right")<net(hurts,"left")
        assert abs(net(neutral,"right")-net(neutral,"left"))<1e-8
        assert neutral["comparison"]["left"]["executed"]==neutral["comparison"]["right"]["executed"]
        assert helps["comparison"]["right"]["attrition"].get("REGIME_ABSTAIN",0)>0
        assert hurts["comparison"]["right"]["attrition"].get("REGIME_ABSTAIN",0)>0

def test_profiles_are_distinct_and_monitoring_is_observe_only():
    cases=[run_case(f,"GATE_NEUTRAL") for f in FAMILIES]
    assert len({c["manifest_digest"] for c in cases})==3
    assert all(c["comparison"]["left"]["portfolio"]["halted"] is False for c in cases)
