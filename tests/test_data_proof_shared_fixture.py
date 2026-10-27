from aql.data_proof_envelope import verify_envelope
from aql.data_proof_shared_fixture import factory_negative_cases


def test_shared_factory_fixture_is_pinned_and_fail_closed():
    fixture = factory_negative_cases()
    envelope = fixture["envelope"]
    versions = verify_envelope(envelope, consumer="factory", minimum_epoch=1,
                               pinned_sha256=fixture["pinned_sha256"])
    assert len(versions) == 3
    for version in versions:
        assert version.eligibility(fixture["decision_cutoff_ms"]) == (
            fixture["expected_local_status"][version.version_id])
    assert envelope["gap_states"]["gap:unknown"] == fixture["expected_gap"]
    assert envelope["provenance_scope"] == "LOCAL_ONLY_UNATTESTED"
    assert fixture["expected_real_pit_admission"] == "REFUSE_UNATTESTED_SOURCE"
