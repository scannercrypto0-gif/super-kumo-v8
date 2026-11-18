"""Synthetic outcome semantics with fixed pre-Scanner denominator.

Counts reflect an explicit supplied slot universe; no real OOS or PIT authority.
"""
from .factory_exam import freeze_manifest, freeze_protocol, run_route, compare_routes


def evaluate_synthetic_outcomes(dna, events, config):
    manifest = freeze_manifest(dna, events)
    protocol = freeze_protocol(manifest, expected_manifest_digest=manifest.digest, config=config)
    always = run_route(manifest, protocol, expected_manifest_digest=manifest.digest,
                       expected_protocol_digest=protocol.digest, arm="ALWAYS")
    regime = run_route(manifest, protocol, expected_manifest_digest=manifest.digest,
                       expected_protocol_digest=protocol.digest, arm="REGIME")
    comparison = compare_routes(always, regime).spec
    return dict(scope="SYNTHETIC_ONLY", scheduled=len(manifest.spec["rows"]),
                always=always.spec, regime=regime.spec, comparison=comparison)
