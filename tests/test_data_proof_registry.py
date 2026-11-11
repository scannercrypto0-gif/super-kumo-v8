import pytest

from aql.data_proof import ObservationVersion, ProofError
from aql.data_proof_registry import RevisionRegistry


def _version(n, *, previous=None, first_seen=1000):
    return ObservationVersion(
        logical_bar_id="BTCUSDT:1m:0", version_number=n,
        payload_digest=("a" if n == 1 else "b") * 64,
        bar_open_ms=0, bar_close_ms=999, first_local_seen_ms=first_seen,
        source_id="binance_ws", supersedes_version_id=previous,
        clock_evidence_ref="local:clock", local_commit_evidence_ref="journal:receipt", ingest_committed_ms=first_seen + 1)


def test_persist_reopen_revision_history_and_idempotent_replay(tmp_path):
    path = tmp_path / "proof.db"
    registry = RevisionRegistry(path)
    original = _version(1)
    correction = _version(2, previous=original.version_id, first_seen=8000)
    assert registry.append(original) == "APPENDED"
    assert registry.append(original) == "ALREADY_PRESENT"
    assert registry.append(correction) == "APPENDED"
    registry.close()
    registry = RevisionRegistry(path)
    assert [v.version_id for v in registry.revisions(original.logical_bar_id)] == [
        original.version_id, correction.version_id]
    assert correction.eligibility(3000) == "REJECT_LATE"
    registry.close()


def test_bad_ancestry_cannot_partially_write(tmp_path):
    registry = RevisionRegistry(tmp_path / "proof.db")
    first = _version(1)
    registry.append(first)
    with pytest.raises(ProofError):
        registry.append(_version(2, previous="wrong", first_seen=8000))
    assert len(registry.revisions(first.logical_bar_id)) == 1
    registry.close()


def test_replay_with_changed_digest_is_not_idempotent(tmp_path):
    registry = RevisionRegistry(tmp_path / "proof.db")
    first = _version(1)
    registry.append(first)
    changed = ObservationVersion(**{**first.__dict__, "payload_digest": "f" * 64})
    with pytest.raises(ProofError):
        registry.append(changed)
    assert registry.revisions(first.logical_bar_id) == (first,)
    registry.close()
