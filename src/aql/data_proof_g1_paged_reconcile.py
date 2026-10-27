"""Cursor-driven bounded proof reconciliation across persisted journal rows.

The returned cursor is a progress hint, not a durable checkpoint. A caller
must persist it only after accepting failures policy; retrying is idempotent.
"""
from aql.data_proof import ProofError
from aql.data_proof_g1_writer import G1RevisionWriter


def reconcile_persisted_page(journal, registry, *, symbol: str, interval: str,
                             after_entry_id: int = 0, limit: int = 256) -> dict:
    if type(after_entry_id) is not int or after_entry_id < 0:
        raise ProofError("invalid journal cursor")
    if type(limit) is not int or not 1 <= limit <= 10000:
        raise ProofError("invalid bounded page size")
    bars = journal.replay(symbol, interval, persisted_only=True,
                          after_entry_id=after_entry_id, limit=limit)
    cursor = after_entry_id
    added = existing = 0
    writer = G1RevisionWriter(registry)
    for bar in bars:
        row_id = getattr(bar, "_journal_entry_id", None)
        if type(row_id) is not int or row_id <= cursor:
            raise ProofError("journal did not return a strictly increasing cursor")
        try:
            result = writer.observe(bar)
        except Exception:
            # Do not advance past failed evidence: retry from last safe cursor.
            return {"next_cursor": cursor, "added": added, "existing": existing,
                    "failed_key": bar.stable_key(), "complete": False}
        added += result == "APPENDED"
        existing += result == "ALREADY_PRESENT"
        cursor = row_id
    return {"next_cursor": cursor, "added": added, "existing": existing,
            "failed_key": None, "complete": len(bars) < limit}
