import copy

import pytest

from aql.data_proof import ObservationVersion, ProofError
from aql.data_proof_envelope import export_envelope, verify_envelope


def _version(n=1, *, first_seen=1000, previous=None):
    return ObservationVersion(
        logical_bar_id="BTCUSDT:1m:0", version_number=n,
        payload_digest=("a" if n == 1 else "b") * 64,
        bar_open_ms=0, bar_close_ms=999, first_local_seen_ms=first_seen,
        source_id="binance_ws", supersedes_version_id=previous,
        clock_evidence_ref="clock:local", local_commit_evidence_ref="journal:receipt")


def test_factory_envelope_replay_preserves_revision_cutoff_and_gap():
    original = _version()
    correction = _version(2, first_seen=8000, previous=original.version_id)
    envelope = export_envelope(consumer="factory", epoch=4,
                               versions=(original, correction),
                               gap_states={"missing:3": "IN_DOUBT"})
    accepted = verify_envelope(envelope, consumer="factory", minimum_epoch=4,
                               pinned_sha256=envelope["manifest_sha256"])
    assert accepted == (original, correction)
    assert accepted[0].eligibility(3000) == "LOCAL_EVIDENCE_ONLY"
    assert accepted[1].eligibility(3000) == "REJECT_LATE"
    assert envelope["gap_states"]["missing:3"] == "IN_DOUBT"


def test_manifest_tamper_and_stale_epoch_rejected():
    envelope = export_envelope(consumer="factory", epoch=4, versions=(_version(),))
    changed = copy.deepcopy(envelope)
    changed["versions"][0]["record"]["first_local_seen_ms"] = 0
    with pytest.raises(ProofError):
        verify_envelope(changed, consumer="factory", minimum_epoch=4,
                        pinned_sha256=envelope["manifest_sha256"])
    with pytest.raises(ProofError):
        verify_envelope(envelope, consumer="factory", minimum_epoch=5,
                        pinned_sha256=envelope["manifest_sha256"])


def test_broken_revision_ancestry_cannot_be_exported():
    with pytest.raises(ProofError):
        export_envelope(consumer="factory", epoch=1,
                        versions=(_version(), _version(2, first_seen=8000, previous="bad")))


def test_missing_first_seen_is_preserved_not_fabricated():
    original = _version(first_seen=None)
    envelope = export_envelope(consumer="factory", epoch=1, versions=(original,))
    versions = verify_envelope(envelope, consumer="factory", minimum_epoch=1,
                               pinned_sha256=envelope["manifest_sha256"])
    assert versions[0].eligibility(3000) == "UNKNOWN_PENDING_EVIDENCE"
