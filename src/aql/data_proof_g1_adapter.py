"""Conservative G1 MarketBar -> Core observation proof adapter.

Local arrival is not provider publication. The existing G1 journal's receipt
is NOT imported as a provider attestation or post-commit timestamp.
"""
from aql.data_proof import ObservationVersion, ProofError


def from_persisted_market_bar(bar, *, version_number: int = 1,
                              supersedes_version_id: str | None = None,
                              local_commit_evidence_ref: str | None = None
                              ) -> ObservationVersion:
    if bar.is_final is not True:
        raise ProofError("non-final G1 bar cannot enter revision custody")
    checksum = bar.compute_checksum()
    if bar.checksum is not None and bar.checksum != checksum:
        raise ProofError("G1 bar payload checksum mismatch")
    return ObservationVersion(
        logical_bar_id=bar.stable_key(),
        version_number=version_number,
        payload_digest=checksum,
        bar_open_ms=bar.bar_open,
        bar_close_ms=bar.bar_close,
        first_local_seen_ms=bar.ingested_at,
        source_id=bar.source,
        supersedes_version_id=supersedes_version_id,
        local_commit_evidence_ref=local_commit_evidence_ref,
        # G1 ingested_at is LOCAL wall-clock, not independently clock attested.
        clock_evidence_ref=None,
        ingest_committed_ms=None,
        provider_available_ms=None,
        provider_evidence_ref=None,
    )
