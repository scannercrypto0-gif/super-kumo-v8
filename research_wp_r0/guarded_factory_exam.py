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

def freeze_manifest_computed_guarded(dna, events, *, computed_by_event,
                                     scanner_vectors, decision_vectors):
    """M18 strict opt-in: validate independently computed results before Scanner.

    computed_by_event[event_id][reference] = {
       "results": tuple[VectorResult], "manifest": VectorManifest,
       "as_of_ms": int, "observed_at_ms": int, "available_at_ms": int
    }
    Receipt timestamps are caller-provided SYNTHETIC evidence only. Never real PIT.
    """
    from .strategy_definition import canonical
    from .strategy_dna_v2 import reference_digest
    from .indicator_library_v2 import VectorManifest
    if type(computed_by_event) is not dict or type(events) is not list:
        raise ValueError("M18 computed feature proof required")
    if set(computed_by_event) != {e["event_id"] for e in events}:
        raise ValueError("M18 event evidence coverage mismatch")
    if set(scanner_vectors) != set(decision_vectors):
        raise ValueError("M18 missing cross-consumer identity")
    expected_refs = {ref["name"]: ref for ref in dna.spec["indicators"]}
    for event in events:
        if event["features"] is None:
            if computed_by_event[event["event_id"]] not in ({}, None):
                raise ValueError("M18 unsupplied event must not assert computed features")
            continue
        provided = computed_by_event[event["event_id"]]
        if type(provided) is not dict or set(provided) != set(event["features"]):
            raise ValueError("M18 feature evidence coverage mismatch")
        if set(provided) != set(expected_refs):
            raise ValueError("M18 strategy reference evidence incomplete")
        for name, proof in provided.items():
            if type(proof) is not dict or set(proof) != {
                "results", "manifest", "as_of_ms", "observed_at_ms", "available_at_ms"
            }:
                raise ValueError("M18 invalid computed evidence")
            manifest, results = proof["manifest"], proof["results"]
            if not isinstance(manifest, VectorManifest) or not isinstance(results, (list, tuple)):
                raise ValueError("M18 calculated vector required")
            if not manifest.verify(results):
                raise ValueError("M18 computed vector integrity mismatch")
            if (manifest.to_dict() != scanner_vectors.get(name)
                    or manifest.to_dict() != decision_vectors.get(name)):
                raise ValueError("M18 claimed vs computed manifest mismatch")
            ref = expected_refs[name]
            if (manifest.indicator_id != ref["indicator_id"]
                    or manifest.version != ref["version"]
                    or tuple(manifest.parameter_set) != tuple(sorted(ref["parameters"].items()))
                    or manifest.decision_cutoff_ms != event["cutoff_ms"]):
                raise ValueError("M18 reference/version/parameter/cutoff mismatch")
            feature = event["features"][name]
            if (type(feature) is not dict or feature.get("indicator_digest") != reference_digest(ref)
                    or feature.get("source_kind") != "SYNTHETIC"):
                raise ValueError("M18 observation reference/source mismatch")
            times = (proof["as_of_ms"], proof["observed_at_ms"], proof["available_at_ms"])
            if (any(type(v) is not int for v in times)
                    or not 0 <= times[0] <= times[1] <= times[2] <= event["cutoff_ms"]
                    or any(feature.get(k) != v for k, v in zip(
                        ("as_of_ms", "observed_at_ms", "available_at_ms"), times))):
                raise ValueError("M18 unverifiable feature timing")
            if len(results) == 0:
                raise ValueError("M18 empty computed results")
            # Only use the last eligible vector in the frozen, sorted complete prefix.
            selected = results[-1]
            if selected.decision_cutoff_ms != event["cutoff_ms"]:
                raise ValueError("M18 vector cutoff mismatch")
            # Caller must retain the actual close/observation mapping for this
            # selected bar; a bar-open-only result is not an as-of receipt.
            if not selected.bar_open_ms <= times[0]:
                raise ValueError("M18 selected bar after feature as-of")
            values = dict(selected.value)
            observed = feature.get("values")
            if (type(observed) is not dict or set(observed) != set(values)
                    or canonical(observed) != canonical(values)):
                raise ValueError("M18 consumed feature differs from computed vector")
    return freeze_manifest_guarded(dna, events, scanner_vectors=scanner_vectors,
                                   decision_vectors=decision_vectors)
