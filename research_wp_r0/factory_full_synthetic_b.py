"""B: deterministic multi-symbol, multi-regime offline Factory examination.

One synthetic StrategyDNA with Scanner/Decision/Monitoring and two matched
policy arms. These are explicit fixture outcomes, NOT historical alpha or PIT.
"""
import json
from .strategy_dna_v2_example import example
from .factory_exam import (
    freeze_manifest, freeze_protocol, run_route, replay_route, compare_routes,
)

REGIMES = ("UPTREND", "UPTREND", "SIDEWAYS", "SIDEWAYS", "DOWNTREND", "DOWNTREND")
SYMBOLS = ("AAA", "BBB", "CCC")
RETURNS = (.015, -.030, .004, -.008, -.025, .008)

def fixture():
    _, dna, assets = example()
    template = {asset["symbol"]: asset["features"] for asset in assets}
    events = []
    for i, regime in enumerate(REGIMES):
        cutoff = 1000 + i * 1000
        for symbol in SYMBOLS:
            features = json.loads(json.dumps(template[symbol]))
            for obs in features.values():
                obs.update(as_of_ms=cutoff-50, observed_at_ms=cutoff-40,
                           available_at_ms=cutoff-30)
            ret = RETURNS[i] if symbol == "AAA" else (.003 if symbol == "BBB" else -.002)
            events.append(dict(
                event_id="S%02d_%s" % (i,symbol), symbol=symbol, venue="fixture",
                cutoff_ms=cutoff, features=features,
                quotes=[
                    dict(at_ms=cutoff+1,available_at_ms=cutoff+1,price=100),
                    dict(at_ms=cutoff+101,available_at_ms=cutoff+101,price=100*(1+ret))],
                # Explicit synthetic no-fill in one otherwise eligible event.
                fill_fraction=0 if i==1 and symbol=="AAA" else 1,
                regime=dict(kind="AS_OF_SYNTHETIC_SCORE",as_of_ms=cutoff-2,
                            available_at_ms=cutoff-1,
                            score=1 if regime=="UPTREND" else .25 if regime=="SIDEWAYS" else 0),
                protection=None))
    config=dict(schema="factory-exam-protocol-1",seed=20261028,
                capital=1000,notional=100,fee_bps=5,spread_bps=4,
                slippage_bps=3,latency_ms=1,holding_ms=100,
                exit_policy="DNA_EXIT_OR_NATIVE_HORIZON_LONG",
                protection_required=False,regime_threshold=.5,
                regime_max_age_ms=100,trial_id="B_FULL_SYNTHETIC_EXAM",
                registered_at_ms=0,parameter_count=0,overlay=None)
    return dna,events,config

def run_experiment():
    dna,events,config=fixture()
    manifest=freeze_manifest(dna,events)
    protocol=freeze_protocol(manifest,expected_manifest_digest=manifest.digest,
                             config=config)
    def run(arm,p=protocol):
        return run_route(manifest,p,expected_manifest_digest=manifest.digest,
                         expected_protocol_digest=p.digest,arm=arm)
    always,gated=run("ALWAYS"),run("REGIME")
    replay_route(manifest,protocol,always,arm="ALWAYS")
    replay_route(manifest,protocol,gated,arm="REGIME")
    comparison=compare_routes(always,gated)
    stress_cfg=dict(config,trial_id="B_COST_SENSITIVITY",
                    fee_bps=15,spread_bps=10,slippage_bps=10)
    stressed=freeze_protocol(manifest,expected_manifest_digest=manifest.digest,
                             config=stress_cfg)
    sensitivity=compare_routes(always,run("ALWAYS",stressed),sensitivity=True)
    return dict(schema="factory-full-synthetic-b-1",
                scope="SYNTHETIC_OFFLINE_ONLY_NOT_EMPIRICAL",
                conditions=list(REGIMES),scheduled=len(events),
                symbols=list(SYMBOLS),dna_digest=dna.digest,
                manifest_digest=manifest.digest,protocol_digest=protocol.digest,
                monitoring=manifest.spec["monitoring"],
                arms={"ALWAYS":always.spec,"REGIME":gated.spec},
                comparison=comparison.spec,
                cost_sensitivity=sensitivity.spec,
                replay="BOTH_ARMS_EXACT_MATCH",
                source_pit="NOT_VERIFIED",oos="NOT_ACCESSED",
                execution="NO_ORDERS",inference="DESCRIPTIVE_ONLY")

if __name__ == "__main__":
    print(json.dumps(run_experiment(),sort_keys=True,indent=2))
