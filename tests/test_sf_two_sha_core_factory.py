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
