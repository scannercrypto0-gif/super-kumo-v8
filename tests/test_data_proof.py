import pytest

from aql.data_proof import ObservationVersion, ProofError, verify_chain


def version(number=1, *, seen=1000, previous=None, **kw):
    values = dict(logical_bar_id="BTCUSDT:1m:0", version_number=number,
                  payload_digest=("a" if number == 1 else "b") * 64,
                  bar_open_ms=0, bar_close_ms=999, first_local_seen_ms=seen,
                  source_id="binance_ws", supersedes_version_id=previous,
                  clock_evidence_ref="clock:local", local_commit_evidence_ref="journal:receipt", ingest_committed_ms=seen + 1)
    values.update(kw)
    return ObservationVersion(**values)


def test_late_correction_cannot_rewrite_earlier_decision():
    first = version()
    corrected = version(2, seen=7000, previous=first.version_id)
    verify_chain((first, corrected))
    assert first.version_id != corrected.version_id
    assert first.eligibility(3000) == "LOCAL_EVIDENCE_ONLY"
    assert corrected.eligibility(3000) == "REJECT_LATE"


def test_missing_arrival_or_receipt_is_unknown():
    assert version(first_local_seen_ms=None).eligibility(3000) == "UNKNOWN_PENDING_EVIDENCE"
    assert version(local_commit_evidence_ref=None, ingest_committed_ms=None).eligibility(3000) == "UNKNOWN_PENDING_EVIDENCE"


def test_unattested_provider_time_rejected():
    with pytest.raises(ProofError):
        version(provider_available_ms=500)


def test_broken_correction_chain_rejected():
    first = version()
    with pytest.raises(ProofError):
        verify_chain((first, version(2, previous="wrong")))


def test_provider_time_after_decision_rejects_even_if_local_timestamp_is_early():
    assert version(provider_available_ms=4000, provider_evidence_ref="provider:attested").eligibility(3000) == "REJECT_LATE"
