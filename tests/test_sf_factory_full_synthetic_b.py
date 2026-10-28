"""Acceptance for option B: matched 18-slot synthetic Factory examination."""
from copy import deepcopy
from research_wp_r0.factory_full_synthetic_b import fixture,run_experiment,REGIMES,SYMBOLS
from research_wp_r0.factory_exam import freeze_manifest,freeze_protocol,run_route,replay_route,compare_routes

def test_full_experiment_covers_all_scheduled_cross_sections():
    report=run_experiment()
    assert report["scope"]=="SYNTHETIC_OFFLINE_ONLY_NOT_EMPIRICAL"
    assert report["scheduled"]==len(REGIMES)*len(SYMBOLS)==18
    assert len(report["monitoring"])==18
    a=report["arms"]["ALWAYS"]["outcomes"]
    b=report["arms"]["REGIME"]["outcomes"]
    assert [x["event_id"] for x in a]==[x["event_id"] for x in b]
    assert len({x["event_id"] for x in a})==18
    assert report["comparison"]["left"]["scheduled"]==18
    assert report["comparison"]["right"]["scheduled"]==18
    assert report["comparison"]["comparison_kind"]=="MATCHED_ASSUMPTIONS"
    assert report["replay"]=="BOTH_ARMS_EXACT_MATCH"
    assert report["oos"]=="NOT_ACCESSED"
    assert report["execution"]=="NO_ORDERS"

def test_gate_abstention_and_nonfill_are_distinct_from_scanner_exclusion():
    report=run_experiment()
    always={x["event_id"]:x for x in report["arms"]["ALWAYS"]["outcomes"]}
    gated={x["event_id"]:x for x in report["arms"]["REGIME"]["outcomes"]}
    assert always["S00_AAA"]["status"]=="EXECUTED"
    assert gated["S00_AAA"]["status"]=="EXECUTED"
    assert always["S01_AAA"]["status"]=="NO_FILL"
    assert gated["S01_AAA"]["status"]=="NO_FILL"
    assert always["S02_AAA"]["status"]=="EXECUTED"
    assert gated["S02_AAA"]["reason"]=="REGIME_ABSTAIN"
    assert always["S04_AAA"]["status"]=="EXECUTED"
    assert gated["S04_AAA"]["reason"]=="REGIME_ABSTAIN"
    assert all(always["S%02d_CCC"%i]["status"]=="ZERO_EXPOSURE" for i in range(6))
    assert report["cost_sensitivity"]["comparison_kind"]=="SENSITIVITY"

def test_replaying_r0_and_source_fingerprints_is_deterministic():
    dna,events,config=fixture()
    manifest=freeze_manifest(dna,events)
    protocol=freeze_protocol(manifest,expected_manifest_digest=manifest.digest,config=config)
    def simulate(arm):
        return run_route(manifest,protocol,expected_manifest_digest=manifest.digest,
                         expected_protocol_digest=protocol.digest,arm=arm)
    a,b=simulate("ALWAYS"),simulate("REGIME")
    assert replay_route(manifest,protocol,a,arm="ALWAYS").digest==a.digest
    assert replay_route(manifest,protocol,b,arm="REGIME").digest==b.digest
    assert compare_routes(a,b).spec["conditional_selection_sensitive"] is True
    assert all(x["source_fingerprint"]==y["source_fingerprint"]
               for x,y in zip(a.spec["outcomes"],b.spec["outcomes"]))
    assert run_experiment()["manifest_digest"]==manifest.digest
