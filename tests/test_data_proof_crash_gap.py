from aql.data_proof import ObservationVersion
from aql.data_proof_registry import RevisionRegistry


def test_crash_gap_is_reported_unknown_after_reopen(tmp_path):
    path = tmp_path / "registry.sqlite"
    registry = RevisionRegistry(path)
    version = ObservationVersion(
        logical_bar_id="ETH:1m:0", version_number=1,
        payload_digest="b" * 64, bar_open_ms=0, bar_close_ms=999,
        first_local_seen_ms=1000, source_id="ws")
    assert registry.append(version) == "APPENDED"
    # Model process death after revision COMMIT and before separate receipt COMMIT.
    registry._db.execute("DELETE FROM postcommit_receipts WHERE version_id=?",
                         (version.version_id,))
    registry.close()
    reopened = RevisionRegistry(path)
    assert reopened.receipt_status(version.version_id) == "UNKNOWN_PENDING_EVIDENCE"
    assert reopened.missing_receipt_versions() == (version.version_id,)
    assert reopened.append(version) == "ALREADY_PRESENT"
    assert reopened.postcommit_receipt(version.version_id) is None
    assert reopened.receipt_status("unknown") == "UNKNOWN_VERSION"
    reopened.close()
