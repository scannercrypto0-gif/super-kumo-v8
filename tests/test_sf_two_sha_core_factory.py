"""Pinned dual-branch Core producer to Factory consumer: synthetic only.

This test requires CORE_PROOF_SOURCE_ROOT to point to a separately fetched,
immutable Core #137 source tree. Never run against a moving branch.
"""
import os
import sys
from pathlib import Path

import pytest
from research_wp_r0.core_proof_bridge import review_core_envelope

CORE_SHA = "0c0108a072f9e0ed780dc0b780c75ff2f24a4840"


def test_real_core_fixture_export_to_factory_negative_admission():
    root = os.environ.get("CORE_PROOF_SOURCE_ROOT")
    if not root:
        pytest.skip("Pinned Core source checkout required for dual-SHA test")
    assert Path(root, "src/aql/data_proof_shared_fixture.py").is_file()
    sys.path.insert(0, str(Path(root, "src")))
    try:
        from aql.data_proof_shared_fixture import factory_negative_cases
        bundle = factory_negative_cases()
        results = review_core_envelope(
            bundle["envelope"], pinned_digest=bundle["pinned_sha256"],
            cutoff_ms=bundle["decision_cutoff_ms"])
        assert len(results) == 3
        assert [v.status for v in results] == [
            "UNKNOWN_PENDING_EVIDENCE", "REJECT_FOR_EMPIRICAL",
            "UNKNOWN_PENDING_EVIDENCE"]
        assert results[1].reason == "NOT_KNOWN_AT_CUTOFF"
        assert not any(v.empirical_eligible or v.real_pit_accepted for v in results)
        assert bundle["expected_real_pit_admission"] == "REFUSE_UNATTESTED_SOURCE"
    finally:
        sys.path.pop(0)

def test_actual_core_fixture_preserves_four_scheduled_slots():
    root = os.environ.get("CORE_PROOF_SOURCE_ROOT")
    if not root:
        pytest.skip("Pinned Core source checkout required")
    sys.path.insert(0, str(Path(root, "src")))
    try:
        from aql.data_proof_shared_fixture import factory_negative_cases
        from research_wp_r0.pre_indicator_boundary import block_unproven_opportunities
        bundle = factory_negative_cases()
        versions = bundle["envelope"]["versions"]
        assert len(versions) == 3
        scheduled = [
            {"event_id": "original", "version_id": versions[0]["version_id"]},
            {"event_id": "late_correction", "version_id": versions[1]["version_id"]},
            {"event_id": "missing_first_seen", "version_id": versions[2]["version_id"]},
            {"event_id": "unprovided", "version_id": "not-in-Core"},
        ]
        receipt = block_unproven_opportunities(
            scheduled=scheduled, envelope=bundle["envelope"],
            pinned_digest=bundle["pinned_sha256"],
            cutoff_ms=bundle["decision_cutoff_ms"])
        assert receipt["scheduled_total"] == receipt["blocked_total"] == 4
        assert [s["reason"] for s in receipt["slots"]] == [
            "PROVIDER_AS_OF_UNVERIFIED", "NOT_KNOWN_AT_CUTOFF",
            "SPARSE_OR_UNCONFIRMED", "NO_CORE_REVISION_RECEIPT"]
        assert not any(s["indicator_features"] is not None or
                       s["execution_request"] is not None
                       for s in receipt["slots"])
    finally:
        sys.path.pop(0)

def test_same_pinned_core_chain_stays_blocked_through_existing_r0():
    """Four Core producer-linked slots reach R0 as UNKNOWN, never fictitious trades."""
    root = os.environ.get("CORE_PROOF_SOURCE_ROOT")
    if not root:
        pytest.skip("Pinned Core source checkout required")
    import copy
    from research_wp_r0.pre_indicator_boundary import block_unproven_opportunities
    from research_wp_r0.factory_exam_example import fixture
    from research_wp_r0.factory_exam import freeze_manifest, freeze_protocol, run_route
    sys.path.insert(0, str(Path(root, "src")))
    try:
        from aql.data_proof_shared_fixture import factory_negative_cases
        bundle = factory_negative_cases()
    finally:
        sys.path.pop(0)
    ids = [item["version_id"] for item in bundle["envelope"]["versions"]]
    scheduled = [{"event_id": f"CORE_SLOT_{i}", "version_id": v}
                 for i, v in enumerate([*ids, "not-delivered"], 1)]
    guarded = block_unproven_opportunities(
        scheduled=scheduled, envelope=bundle["envelope"],
        pinned_digest=bundle["pinned_sha256"],
        cutoff_ms=bundle["decision_cutoff_ms"])
    assert guarded["scheduled_total"] == guarded["blocked_total"] == 4
    dna, template, config = fixture()
    events = []
    for i, row in enumerate(guarded["slots"]):
        event = copy.deepcopy(template[i])
        event["event_id"] = row["event_id"]
        event["cutoff_ms"] = bundle["decision_cutoff_ms"] + i * 1000
        event["features"] = row["indicator_features"]
        event["quotes"] = []
        event["regime"] = None
        event["fill_fraction"] = None
        events.append(event)
    manifest = freeze_manifest(dna, events)
    protocol = freeze_protocol(manifest, expected_manifest_digest=manifest.digest,
                               config=config)
    for arm in ("ALWAYS", "REGIME"):
        receipt = run_route(manifest, protocol,
                            expected_manifest_digest=manifest.digest,
                            expected_protocol_digest=protocol.digest, arm=arm).spec
        assert len(receipt["outcomes"]) == guarded["scheduled_total"]
        assert [x["event_id"] for x in receipt["outcomes"]] == [x["event_id"] for x in events]
        assert all(x["status"] == "UNKNOWN" for x in receipt["outcomes"])
        assert not any(item["kind"] == "SIMULATED_ENTRY" for item in receipt["ledger"])
