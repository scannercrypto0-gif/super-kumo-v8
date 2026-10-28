"""Bounded, read-only journal scan to repair missing LOCAL observation records.

Only PERSISTED journal rows are eligible; the journal remains the source of
truth. Reconstructed evidence never receives a new arrival or commit time.
This offline control-plane operation must not run on the G1 hot path.
"""
from aql.data_proof import ProofError
from aql.data_proof_g1_writer import G1RevisionWriter


def reconcile_persisted_observations(journal, registry, *,
                                     symbol: str, interval: str,
                                     limit: int = 1000) -> dict:
    if type(limit) is not int or not 1 <= limit <= 10000:
        raise ProofError("bounded reconciliation limit required")
    # Journal replay validates each payload checksum and excludes quarantined
    # keys by default. A bounded prefix does NOT prove full coverage.
    bars = journal.replay(symbol, interval, persisted_only=True, limit=limit)
    writer = G1RevisionWriter(registry)
    added = 0
    existing = 0
    failures = []
    for bar in bars:
        # Only confirmed operational-store persisted entries; do not promote
        # LOCAL_COMMITTED into PERSISTED based on this evidence scan.
        try:
            result = writer.observe(bar)
            if result == "APPENDED":
                added += 1
            else:
                existing += 1
        except Exception as exc:
            failures.append((bar.stable_key(), type(exc).__name__))
    return {"scanned": len(bars), "added": added, "existing": existing,
            "failures": tuple(failures), "bounded_prefix_only": True}
