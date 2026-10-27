"""Shared deterministic Core producer cases for Factory offline admission.

Fixtures are synthetic, not issuer-verified and never evidence of real PIT.
"""
from aql.data_proof import ObservationVersion
from aql.data_proof_envelope import export_envelope


def factory_negative_cases() -> dict:
    original = ObservationVersion(
        logical_bar_id="BTCUSDT:1m:0", version_number=1,
        payload_digest="a" * 64, bar_open_ms=0, bar_close_ms=59999,
        first_local_seen_ms=60001, source_id="synthetic-ws",
        clock_evidence_ref="synthetic-clock",
        local_commit_evidence_ref="synthetic-local-receipt",
        ingest_committed_ms=60002)
    late = ObservationVersion(
        logical_bar_id=original.logical_bar_id, version_number=2,
        payload_digest="b" * 64, bar_open_ms=0, bar_close_ms=59999,
        first_local_seen_ms=90000, source_id="synthetic-ws",
        supersedes_version_id=original.version_id,
        clock_evidence_ref="synthetic-clock",
        local_commit_evidence_ref="synthetic-local-receipt",
        ingest_committed_ms=90001)
    missing = ObservationVersion(
        logical_bar_id="ETHUSDT:1m:0", version_number=1,
        payload_digest="c" * 64, bar_open_ms=0, bar_close_ms=59999,
        first_local_seen_ms=None, source_id="synthetic-ws")
    envelope = export_envelope(
        consumer="factory", epoch=1, versions=(original, late, missing),
        gap_states={"gap:unknown": "IN_DOUBT"})
    return {
        "decision_cutoff_ms": 70000,
        "envelope": envelope,
        "pinned_sha256": envelope["manifest_sha256"],
        "expected_local_status": {
            original.version_id: "LOCAL_EVIDENCE_ONLY",
            late.version_id: "REJECT_LATE",
            missing.version_id: "UNKNOWN_PENDING_EVIDENCE"},
        "expected_gap": "IN_DOUBT",
        "expected_real_pit_admission": "REFUSE_UNATTESTED_SOURCE",
        "trust_scope": "SYNTHETIC_LOCAL_ONLY",
    }
