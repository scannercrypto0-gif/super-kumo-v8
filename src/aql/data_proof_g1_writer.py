"""Opt-in registry writer for persisted G1 MarketBar observations.

A duplicate is idempotent. Conflicting content is never silently overwritten:
G1 legacy source treats it as a conflict until an authorized correction source
with independent ordering/evidence is defined.
"""
from aql.data_proof import ProofError
from aql.data_proof_g1_adapter import from_persisted_market_bar


class G1RevisionWriter:
    def __init__(self, registry):
        self.registry = registry

    def observe(self, bar, *, local_commit_evidence_ref: str | None = None) -> str:
        existing = self.registry.revisions(bar.stable_key())
        candidate = from_persisted_market_bar(
            bar, local_commit_evidence_ref=local_commit_evidence_ref)
        if existing:
            if existing[0].payload_digest != candidate.payload_digest:
                raise ProofError("G1_CONTENT_CONFLICT_REQUIRES_AUTHORIZED_REVISION")
            return "ALREADY_PRESENT"
        return self.registry.append(candidate)
