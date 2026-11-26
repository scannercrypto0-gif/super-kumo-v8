"""Explicit opt-in composition of G1 post-persist observation custody.

Failure cannot roll back G1 ACK. A durable journal scan is still required
for missed observations after crash; this is not a complete replay mechanism.
"""
from aql.data_proof_g1_writer import G1RevisionWriter


def make_g1_revision_observer(registry):
    writer = G1RevisionWriter(registry)

    def after_persisted(bar):
        # A journal receipt is intentionally NOT synthesized from stable_key().
        # No postcommit or provider timing is inferred here.
        writer.observe(bar)

    return after_persisted
