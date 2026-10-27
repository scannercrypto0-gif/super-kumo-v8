"""Explicit opt-in M18 guarded synthetic Factory exam boundary.

Caller-owned manifests are only checked for equality, not independently
authenticated as the feature vectors that generated the synthetic observations.
"""
from .factory_exam import freeze_manifest
from .indicator_calculation_identity import require_same_calculation


def freeze_manifest_guarded(dna, events, *, scanner_vectors, decision_vectors):
    """Reject mismatched feature calculation identities before Scanner/Decision."""
    if (type(scanner_vectors) is not dict or type(decision_vectors) is not dict
            or not scanner_vectors or set(scanner_vectors) != set(decision_vectors)):
        raise ValueError("M18 complete paired vector manifests required")
    identities = {}
    for reference in sorted(scanner_vectors):
        if type(reference) is not str or not reference:
            raise ValueError("M18 invalid feature reference")
        identities[reference] = require_same_calculation(
            scanner_vectors[reference], decision_vectors[reference])
    # Existing accepted R0 path, still purely synthetic and no actual provenance.
    return freeze_manifest(dna, events), identities
