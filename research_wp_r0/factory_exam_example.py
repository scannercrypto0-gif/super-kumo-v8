"""Frozen eight-slot arithmetic counterexample; NOT empirical regime alpha."""
import json

from .factory_exam import freeze_manifest, freeze_protocol, run_route, compare_routes
from .strategy_dna_v2_example import example


def fixture():
    _, dna, assets = example()
    returns = [.01, -.04, .012, -.05, .009, -.03, .011, -.045]
    events = []
    for i, ret in enumerate(returns):
        cutoff = 1000+i*1000
        features = json.loads(json.dumps(assets[0]["features"]))
        for obs in features.values():
            obs.update(as_of_ms=cutoff-50, observed_at_ms=cutoff-40, available_at_ms=cutoff-30)
        events.append(dict(event_id="E%d" % i, cutoff_ms=cutoff, symbol="AAA", venue="fixture",
            features=features, quotes=[dict(at_ms=cutoff+1, available_at_ms=cutoff+1, price=100),
                                       dict(at_ms=cutoff+101, available_at_ms=cutoff+101, price=100*(1+ret))],
            fill_fraction=1, regime=dict(kind="AS_OF_SYNTHETIC_SCORE", as_of_ms=cutoff-1,
                available_at_ms=cutoff, score=1 if i%2==0 else 0), protection=None))
    config = dict(schema="factory-exam-protocol-1", seed=20261027, capital=1000,
        notional=100, fee_bps=0, spread_bps=0, slippage_bps=0, latency_ms=1,
        holding_ms=100, exit_policy="DNA_EXIT_OR_NATIVE_HORIZON_LONG", protection_required=False,
        regime_threshold=.5, regime_max_age_ms=100, trial_id="ARITHMETIC_R0",
        registered_at_ms=0, parameter_count=0, overlay=None)
    return dna, events, config


def run_fixture():
    dna, events, config = fixture()
    manifest = freeze_manifest(dna, events)
    def protocol(cfg):
        return freeze_protocol(manifest, expected_manifest_digest=manifest.digest, config=cfg)
    def route(p, arm="ALWAYS"):
        return run_route(manifest, p, expected_manifest_digest=manifest.digest,
                         expected_protocol_digest=p.digest, arm=arm)
    base = protocol(config)
    always, gated = route(base), route(base, "REGIME")
    # Frozen sensitivity designs; no threshold fitting or held-out observations.
    costly = protocol(dict(config, trial_id="BASE_COST", fee_bps=10, slippage_bps=5, spread_bps=2))
    stress = protocol(dict(config, trial_id="COST_STRESS", fee_bps=20, slippage_bps=10, spread_bps=4))
    overlay = protocol(dict(config, trial_id="R1_SINGLE_OVERLAY",
                            overlay=dict(name="MAX_CONCURRENT", version="1", max_concurrent=1)))
    r1 = route(overlay)
    return dict(scope="SYNTHETIC_OFFLINE_ONLY", seed=config["seed"], manifest_digest=manifest.digest,
        protocol_digests=[p.digest for p in (base, costly, stress, overlay)],
        trial_register=[dict(trial_id=p.spec["config"]["trial_id"], protocol_digest=p.digest,
                             parameter_count=p.spec["config"]["parameter_count"], registered_at_ms=0)
                        for p in (base, costly, stress, overlay)],
        fixture="M10_ARITHMETIC_COUNTEREXAMPLE_HANDCRAFTED_NOT_PREDICTIVE_EVIDENCE",
        r0_comparison=compare_routes(always, gated).spec,
        r1_comparison=compare_routes(always, r1, sensitivity=True).spec,
        r1_regime_comparison=compare_routes(gated, route(overlay,"REGIME"), sensitivity=True).spec,
        cost_sensitivity=compare_routes(route(costly), route(stress), sensitivity=True).spec,
        r2="NOT_IMPLEMENTED_NO_VALIDATED_OVERLAY_COMBINATION",
        inference="NO_P_VALUES_NO_CALIBRATED_SIGNIFICANCE_NO_PROMOTION",
        real_readiness="BLOCKED_BY_PIT_REGIME_PROVENANCE_REAL_FILL_MODEL")


if __name__ == "__main__":
    print(json.dumps(run_fixture(), sort_keys=True, indent=2))
