"""Core M16/M17: local receipts are not issuer-time or correction-first-known proof."""
from unittest.mock import patch

import pytest

from aql.data_proof import ObservationVersion, ProofError
from aql.data_proof_registry import RevisionRegistry
from aql.data_proof_envelope import export_envelope, verify_envelope


def _version(n, previous=None, seen=1000):
    return ObservationVersion(
        logical_bar_id="BTCUSDT:1m:0", version_number=n,
        payload_digest=("a" if n == 1 else "b") * 64,
        bar_open_ms=0, bar_close_ms=59999, first_local_seen_ms=seen,
        source_id="synthetic", supersedes_version_id=previous)


def test_postcommit_receipt_gap_survives_restart_without_retroactive_timestamp(tmp_path):
    path = tmp_path / "proof.sqlite"
    first = _version(1)
    registry = RevisionRegistry(path)
    with patch("aql.data_proof_registry.time.time_ns", side_effect=OSError("clock unavailable")):
        with pytest.raises(OSError, match="clock unavailable"):
            registry.append(first)
    assert registry.revisions(first.logical_bar_id) == (first,)
    assert registry.receipt_status(first.version_id) == "UNKNOWN_PENDING_EVIDENCE"
    registry.close()

    reopened = RevisionRegistry(path)
    assert reopened.append(first) == "ALREADY_PRESENT"
    assert reopened.receipt_status(first.version_id) == "UNKNOWN_PENDING_EVIDENCE"
    assert reopened.missing_receipt_versions() == (first.version_id,)
    assert reopened.postcommit_receipt(first.version_id) is None
    reopened.close()


def test_correction_never_inherits_first_version_receipt_or_provider_time(tmp_path):
    registry = RevisionRegistry(tmp_path / "proof.sqlite")
    original = _version(1)
    correction = _version(2, original.version_id, seen=9000)
    registry.append(original)
    assert registry.receipt_status(original.version_id) == "POSTCOMMIT_LOCAL_OBSERVED"
    with patch("aql.data_proof_registry.time.time_ns", side_effect=OSError("clock unavailable")):
        with pytest.raises(OSError):
            registry.append(correction)
    assert registry.receipt_status(correction.version_id) == "UNKNOWN_PENDING_EVIDENCE"
    assert registry.postcommit_receipt(correction.version_id) is None
    assert correction.eligibility(5000) == "REJECT_LATE"
    registry.close()


def test_local_export_is_not_provider_attestation():
    first = _version(1)
    envelope = export_envelope(consumer="factory", epoch=1, versions=(first,))
    assert envelope["provenance_scope"] == "LOCAL_ONLY_UNATTESTED"
    assert verify_envelope(envelope, consumer="factory", minimum_epoch=1,
                           pinned_sha256=envelope["manifest_sha256"]) == (first,)
    assert first.provider_available_ms is None
    assert first.provider_evidence_ref is None
    assert first.eligibility(5000) == "UNKNOWN_PENDING_EVIDENCE"
