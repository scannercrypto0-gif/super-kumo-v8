"""Reproducible, supplied synthetic scalars; no market access or orders."""
import json
from pathlib import Path
from research_wp_r0.strategy_definition import StrategyDefinition
from research_wp_r0.strategy_dna_v2 import StrategyDNAV2, evaluate_synthetic, reference_digest

def example():
    root = Path(__file__).resolve().parents[1]
    v1 = StrategyDefinition(json.loads((root / "examples/strategy_definition_v1.json").read_text())["definition"])
    def ref(name, indicator):
        return dict(name=name, indicator_id=indicator, version="1",
                    parameters={"period":3}, constraints={"period":{"type":"int","min":2,"max":20}})
    refs = [ref("trend","SMA_v1"), ref("strength","RSI_v1"), ref("observe","ATR_v1")]
    def inp(name): return dict(reference=name,field="value",max_age_ms=100)
    def predicate(name, value):
        return dict(rule_id=name, **inp("trend"), operator="gt",value=value)
    def term(name, weight, direction):
        return dict(term_id=name, **inp(name),weight=weight,lower=0,upper=100,direction=direction)
    spec = dict(schema_version="2",strategy_id="synthetic_roles",strategy_version="v2_1",
        scope="SYNTHETIC_RESEARCH_ONLY",v1_digest=v1.digest,
        v1_link_mode="REFERENCE_ONLY_NO_AST_TRANSLATION",indicators=refs,
        scanner_profile=dict(profile_id="screen",version=1,allowed_symbols=["AAA","BBB","CCC"],
            allowed_venues=["fixture"],filters=[predicate("minimum_trend",10)],
            ranking=[dict(**inp("trend"),direction="DESC")],max_candidates=2,tie_break="SYMBOL_VENUE_ASC"),
        decision_profile=dict(profile_id="decision",version=1,
            normalization="POSITIVE_WEIGHTED_MEAN_CLAMPED_LINEAR_V1",conflict_policy="REJECT_AMBIGUOUS",
            entry=dict(terms=[term("trend",3,"HIGH"),term("strength",1,"HIGH")],
                       threshold=.7,mandatory=[predicate("mandatory_trend",50)]),
            exit=dict(terms=[term("trend",1,"LOW")],threshold=.8,mandatory=[])),
        monitoring_profile=dict(profile_id="monitor",version=1,authority="OBSERVE_ONLY",
            features=[dict(feature_id="volatility",**inp("observe"))]),
        provenance=dict(kind="SYNTHETIC_NOT_AUTHENTICATED",source_generation_id="fixture_v1",
            allowed_sources=["generator"],plan_id="bounded_roles_v1"),
        regime_policy="DEFERRED_NOT_EVALUATED",execution="DISABLED")
    assets = []
    for symbol, trend, strength in [("AAA",90,80),("BBB",40,90),("CCC",5,99)]:
        features = {}
        for r,val in zip(refs,(trend,strength,3)):
            features[r["name"]] = dict(indicator_digest=reference_digest(r),source_kind="SYNTHETIC",
                source_id="generator",source_generation_id="fixture_v1",quality="VALID",
                is_final=True,as_of_ms=950,observed_at_ms=960,available_at_ms=970,values={"value":val})
        assets.append(dict(symbol=symbol,venue="fixture",features=features))
    return v1, StrategyDNAV2(spec,v1_definition=v1), assets

def main():
    _, dna, assets = example()
    print(evaluate_synthetic(dna,assets,decision_cutoff_ms=1000).to_json())

if __name__ == "__main__":
    main()
