"""B2 preregistered synthetic counterfactuals, never market alpha evidence.

Three deliberately distinct StrategyDNA decision profiles, three regime-gate
scenarios (helps, hurts, neutral), and identical scheduled cross-sections.
No live data, PIT claim, optimizer, statistical promotion, or orders.
"""
import json
from copy import deepcopy
from .strategy_dna_v2_example import example
from .strategy_dna_v2 import StrategyDNAV2
from .factory_exam import freeze_manifest,freeze_protocol,run_route,replay_route,compare_routes
from .strategy_definition import digest

FAMILIES=("TREND_FOLLOWING","MEAN_REVERSION","BREAKOUT")
SCENARIOS=("GATE_HELPS","GATE_HURTS","GATE_NEUTRAL")
SYMBOLS=("AAA","BBB","CCC")
WINDOWS=("UPTREND","SIDEWAYS","DOWNTREND","VOLATILE","FALSE_BREAKOUT","RECOVERY")
# Precommitted returns and gate decisions: these are constructed falsifiers,
# NOT observations, results of training, or optimization.
RETURNS={
    "GATE_HELPS":(-.030,.015,-.020,.012,-.010,.010),
    "GATE_HURTS":(.030,.015,.020,.012,.010,.010),
    "GATE_NEUTRAL":(.010,-.010,.015,-.015,.012,-.012),
}
GATES={
    "GATE_HELPS":(0,1,0,1,0,1),
    "GATE_HURTS":(0,1,0,1,0,1),
    "GATE_NEUTRAL":(1,1,1,1,1,1),
}

def strategy(family):
    if family not in FAMILIES:
        raise ValueError("Unknown preregistered synthetic strategy")
    v1,base,assets=example()
    spec=deepcopy(base.spec)
    spec["strategy_id"]="b2_"+family.lower()
    spec["strategy_version"]="b2_v1"
    profile=spec["decision_profile"]
    if family=="MEAN_REVERSION":
        profile["entry"]["terms"]=[dict(term_id="mr_trend",reference="trend",
            field="value",max_age_ms=100,weight=1,lower=0,upper=100,direction="LOW"),
            dict(term_id="mr_strength",reference="strength",field="value",
                 max_age_ms=100,weight=1,lower=0,upper=100,direction="HIGH")]
        profile["entry"]["threshold"]=.7
        profile["entry"]["mandatory"]=[]
        profile["exit"]["terms"]=[dict(term_id="mr_exit",reference="trend",
            field="value",max_age_ms=100,weight=1,lower=0,upper=100,direction="HIGH")]
        profile["exit"]["threshold"]=.95
    elif family=="BREAKOUT":
        profile["entry"]["threshold"]=.65
        profile["entry"]["mandatory"]=[]
        profile["exit"]["threshold"]=.9
    features={x["symbol"]:deepcopy(x["features"]) for x in assets}
    if family=="MEAN_REVERSION":
        features["AAA"]["trend"]["values"]["value"]=20
        features["BBB"]["trend"]["values"]["value"]=60
    elif family=="BREAKOUT":
        features["AAA"]["trend"]["values"]["value"]=80
        features["BBB"]["trend"]["values"]["value"]=35
    return StrategyDNAV2(spec,v1_definition=v1),features

def fixture(family,scenario):
    if scenario not in SCENARIOS:
        raise ValueError("Unknown preregistered scenario")
    dna,templates=strategy(family)
    events=[]
    for i,window in enumerate(WINDOWS):
        cutoff=1000+i*1000
        for symbol in SYMBOLS:
            obs=deepcopy(templates[symbol])
            for value in obs.values():
                value.update(as_of_ms=cutoff-50,observed_at_ms=cutoff-40,
                             available_at_ms=cutoff-30)
            # Precommitted family-specific unfavorable feature windows. These
            # change eligibility, not ex-post result tuning or market returns.
            if symbol=="AAA" and ((family=="MEAN_REVERSION" and i==5)
                                  or (family=="BREAKOUT" and i==3)):
                obs["strength"]["values"]["value"]=10
            ret=RETURNS[scenario][i] if symbol=="AAA" else (.002 if symbol=="BBB" else -.002)
            events.append(dict(
                event_id="B2_%02d_%s"%(i,symbol),symbol=symbol,venue="fixture",
                cutoff_ms=cutoff,features=obs,
                quotes=[dict(at_ms=cutoff+1,available_at_ms=cutoff+1,price=100),
                        dict(at_ms=cutoff+101,available_at_ms=cutoff+101,price=100*(1+ret))],
                fill_fraction=1,
                regime=dict(kind="AS_OF_SYNTHETIC_SCORE",as_of_ms=cutoff-2,
                            available_at_ms=cutoff-1,score=GATES[scenario][i]),
                protection=None))
    config=dict(schema="factory-exam-protocol-1",seed=20261028,
        capital=1000,notional=100,fee_bps=5,spread_bps=4,slippage_bps=3,
        latency_ms=1,holding_ms=100,exit_policy="DNA_EXIT_OR_NATIVE_HORIZON_LONG",
        protection_required=False,regime_threshold=.5,regime_max_age_ms=100,
        trial_id="B2_"+scenario,registered_at_ms=0,parameter_count=0,overlay=None)
    return dna,events,config

def run_case(family,scenario):
    dna,events,config=fixture(family,scenario)
    m=freeze_manifest(dna,events)
    p=freeze_protocol(m,expected_manifest_digest=m.digest,config=config)
    def run(arm):
        return run_route(m,p,expected_manifest_digest=m.digest,
                         expected_protocol_digest=p.digest,arm=arm)
    a,b=run("ALWAYS"),run("REGIME")
    assert replay_route(m,p,a,arm="ALWAYS").digest==a.digest
    assert replay_route(m,p,b,arm="REGIME").digest==b.digest
    comp=compare_routes(a,b).spec
    outcomes_a=a.spec["outcomes"];outcomes_b=b.spec["outcomes"]
    per_opportunity=[dict(event_id=x["event_id"],always_status=x["status"],
        regime_status=y["status"],always_reason=x["reason"],regime_reason=y["reason"],
        always_net=x["net_quote"],regime_net=y["net_quote"],
        paired_net_delta=None if x["net_quote"] is None or y["net_quote"] is None
                         else y["net_quote"]-x["net_quote"])
        for x,y in zip(outcomes_a,outcomes_b)]
    return dict(family=family,scenario=scenario,conditions=list(WINDOWS),
        preregistered_returns=list(RETURNS[scenario]),
        preregistered_gate=list(GATES[scenario]),
        scheduled=len(events),manifest_digest=m.digest,protocol_digest=p.digest,
        monitoring_count=len(m.spec["monitoring"]),
        comparison=comp,opportunity_counterfactuals=per_opportunity,
        replay="EXACT_BOTH",source="AUTHORED_SYNTHETIC_ONLY")

def run_suite():
    cases=[run_case(f,s) for f in FAMILIES for s in SCENARIOS]
    return dict(schema="factory-b2-counterfactual-1",
        scope="SYNTHETIC_OFFLINE_ONLY_NOT_EMPIRICAL",families=list(FAMILIES),
        scenarios=list(SCENARIOS),cases=cases,
        registered_design_digest=digest(dict(families=FAMILIES,scenarios=SCENARIOS,
                                            windows=WINDOWS,returns=RETURNS,gates=GATES)),
        no_alpha_promotion=True,market_pit="NOT_VERIFIED",
        order_io="DISABLED",oos="NOT_ACCESSED")

if __name__=="__main__":
    print(json.dumps(run_suite(),sort_keys=True,indent=2))
