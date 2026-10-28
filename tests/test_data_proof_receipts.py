from aql.data_proof import ObservationVersion
from aql.data_proof_registry import RevisionRegistry


def test_receipt_is_postcommit_and_survives_reopen(tmp_path):
    path = tmp_path / "proof.sqlite"
    registry = RevisionRegistry(path)
    version = ObservationVersion(
        logical_bar_id="BTC:1m:0", version_number=1,
        payload_digest="a" * 64, bar_open_ms=0, bar_close_ms=999,
        first_local_seen_ms=1000, source_id="ws")
    assert registry.append(version) == "APPENDED"
    receipt = registry.postcommit_receipt(version.version_id)
    assert receipt["observed_after_commit_ms"] >= 1000
    assert receipt["clock_scope"] == "LOCAL_WALL_CLOCK_UNATTESTED"
    registry.close()
    reopened = RevisionRegistry(path)
    assert reopened.postcommit_receipt(version.version_id) == receipt
    assert reopened.append(version) == "ALREADY_PRESENT"
    assert reopened.postcommit_receipt(version.version_id) == receipt
    reopened.close()


def test_absent_receipt_does_not_imply_fabricated_commit_time(tmp_path):
    registry = RevisionRegistry(tmp_path / "proof.sqlite")
    assert registry.postcommit_receipt("unknown-version") is None
    registry.close()
