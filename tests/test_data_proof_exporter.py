from aql.data_proof import ObservationVersion
from aql.data_proof_envelope import verify_envelope
from aql.data_proof_exporter import BoundedEvidenceExporter
from aql.data_proof_registry import RevisionRegistry


def test_persistent_registry_to_async_factory_envelope(tmp_path):
    registry = RevisionRegistry(tmp_path / "revisions.db")
    first = ObservationVersion(
        logical_bar_id="BTCUSDT:1m:0", version_number=1,
        payload_digest="a" * 64, bar_open_ms=0, bar_close_ms=999,
        first_local_seen_ms=1000, source_id="ws",
        clock_evidence_ref="local-clock", local_commit_evidence_ref="post-commit")
    second = ObservationVersion(
        logical_bar_id=first.logical_bar_id, version_number=2,
        payload_digest="b" * 64, bar_open_ms=0, bar_close_ms=999,
        first_local_seen_ms=8000, source_id="ws",
        supersedes_version_id=first.version_id,
        clock_evidence_ref="local-clock", local_commit_evidence_ref="post-commit")
    registry.append(first)
    registry.append(second)
    exporter = BoundedEvidenceExporter(registry, capacity=2)
    future = exporter.submit(consumer="factory", epoch=7,
                             logical_bar_id=first.logical_bar_id,
                             gap_states={"gap:2": "IN_DOUBT"})
    envelope = future.result(timeout=5)
    assert envelope["gap_states"]["gap:2"] == "IN_DOUBT"
    versions = verify_envelope(envelope, consumer="factory", minimum_epoch=7,
                               pinned_sha256=envelope["manifest_sha256"])
    assert versions == (first, second)
    assert versions[1].eligibility(3000) == "REJECT_LATE"
    exporter.close()
    registry.close()


def test_missing_revision_fails_explicitly(tmp_path):
    registry = RevisionRegistry(tmp_path / "revisions.db")
    exporter = BoundedEvidenceExporter(registry, capacity=1)
    future = exporter.submit(consumer="factory", epoch=1, logical_bar_id="missing")
    try:
        future.result(timeout=5)
        assert False, "missing revision should fail"
    except ValueError as exc:
        assert "no committed observation" in str(exc)
    exporter.close()
    registry.close()
