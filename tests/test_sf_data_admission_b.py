"""Targeted M16/M17 consumer falsifiers; synthetic receipts only."""
from research_wp_r0.data_admission_b import admit_revision

PIN = "a" * 64
def sample(**changes):
    value = dict(version_id="btc-1", manifest_digest=PIN, gap_state="CONFIRMED",
                 payload_digest="b"*64, bar_close_ms=1201,
                 first_local_seen_ms=1201, ingest_committed_ms=1201,
                 provider_available_ms=1201, provider_evidence_ref="issuer",
                 clock_evidence_ref="clock", supersedes_version_id=None)
    value.update(changes)
    return value

def result(value, cutoff=1202, verified=True):
    return admit_revision(value, cutoff_ms=cutoff, expected_manifest_digest=PIN,
                          verified_source_timing=verified)

def test_late_original_even_with_valid_manifest():
    assert result(sample(first_local_seen_ms=1205, ingest_committed_ms=1205)).status == "REJECT_FOR_EMPIRICAL"

def test_late_revision_does_not_rewrite_past():
    x = sample(version_id="btc-2", supersedes_version_id="btc-1",
               first_local_seen_ms=1210, ingest_committed_ms=1210,
               revision_first_seen_ms=1210)
    assert result(x).status == "REJECT_FOR_EMPIRICAL"

def test_missing_ingest_confirmed_is_unknown():
    assert result(sample(first_local_seen_ms=None, ingest_committed_ms=None)).status == "UNKNOWN_PENDING_EVIDENCE"

def test_sparse_unknown_not_confirmed():
    for state in ("UNKNOWN", "WITHHELD", "IN_DOUBT"):
        assert result(sample(gap_state=state)).status == "UNKNOWN_PENDING_EVIDENCE"

def test_clock_and_provider_evidence_not_inferred_from_hash():
    assert result(sample(), verified=False).status == "UNKNOWN_PENDING_EVIDENCE"
    assert result(sample(provider_available_ms=None)).status == "UNKNOWN_PENDING_EVIDENCE"

def test_version_manifest_and_temporal_inconsistency():
    assert result(sample(manifest_digest="c"*64)).status == "REJECT_FOR_EMPIRICAL"
    assert result(sample(first_local_seen_ms=1200)).status == "REJECT_FOR_EMPIRICAL"

def test_positive_still_not_real_pit():
    receipt = result(sample())
    assert receipt.empirical_eligible and not receipt.real_pit_accepted
