"""Focused M18 consumed-value regression; synthetic source, no market PIT claims."""
import copy
import pytest
from research_wp_r0.factory_exam_example import fixture
from research_wp_r0.guarded_factory_exam import freeze_manifest_computed_guarded
from research_wp_r0.indicator_library_v2 import VectorResult, VectorManifest

def make_proofs(dna, event):
    vectors, manifests = {}, {}
    for ref in dna.spec["indicators"]:
        name = ref["name"]
        values = event["features"][name]["values"]
        result = VectorResult.create(
            indicator_id=ref["indicator_id"], version=ref["version"],
            dataset_id="SYNTHETIC", dataset_version=1,
            dataset_manifest_hash="a"*64,
            bar_open_ms=event["cutoff_ms"]-50,
            decision_cutoff_ms=event["cutoff_ms"],
            value=tuple(sorted(values.items())),
            parameters=tuple(sorted(ref["parameters"].items())),
            warmup_bars_consumed=0, partial_coverage=False)
        meta = dict(indicator_id=result.indicator_id, version=result.version,
            dataset_id=result.dataset_id, dataset_version=result.dataset_version,
            dataset_manifest_hash=result.dataset_manifest_hash,
            decision_cutoff_ms=result.decision_cutoff_ms,
            parameter_set=result.parameters, warmup_policy=0,
            output_fields=[k for k,_ in result.value],
            start_ms=event["cutoff_ms"]-50, end_ms=event["cutoff_ms"],
            input_bar_hash="b"*64)
        manifest = VectorManifest.create(meta, [result])
        vectors[name] = dict(results=[result], manifest=manifest,
            as_of_ms=event["cutoff_ms"]-50,
            observed_at_ms=event["cutoff_ms"]-40,
            available_at_ms=event["cutoff_ms"]-30)
        manifests[name] = manifest.to_dict()
    return vectors, manifests

def test_unchanged_manifests_but_mutated_consumed_value_rejected_before_scanner():
    dna, events, _ = fixture()
    event = copy.deepcopy(events[0])
    proof, manifests = make_proofs(dna,event)
    event["features"]["trend"]["values"]["value"] += 1
    with pytest.raises(ValueError, match="M18 independently recomputable input proof required"):
        freeze_manifest_computed_guarded(dna,[event],computed_by_event={event["event_id"]:proof},
            scanner_vectors=manifests,decision_vectors=copy.deepcopy(manifests))

def test_self_consistent_manufactured_proof_without_independent_source_rejected():
    dna,events,_ = fixture()
    event=copy.deepcopy(events[0])
    proof, manifests=make_proofs(dna,event)
    with pytest.raises(ValueError,match="M18 independently recomputable input proof required"):
        freeze_manifest_computed_guarded(dna,[event],
            computed_by_event={event["event_id"]:proof},
            scanner_vectors=manifests,decision_vectors=copy.deepcopy(manifests))
