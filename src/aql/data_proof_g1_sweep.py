"""Independent bounded full-sweep pass catches late PERSISTED ACKs behind cursor.

The sweep always starts at row zero, ignoring the fast-path checkpoint.
Repeat it periodically under an external scheduler; no hot-path activation.
"""
from aql.data_proof import ProofError
from aql.data_proof_g1_paged_reconcile import reconcile_persisted_page


def sweep_persisted_proofs(journal, registry, *, symbol: str, interval: str,
                           page_size: int = 256, max_pages: int = 100) -> dict:
    if type(max_pages) is not int or not 1 <= max_pages <= 10000:
        raise ProofError("invalid bounded sweep page count")
    cursor = 0
    added = existing = pages = 0
    for _ in range(max_pages):
        result = reconcile_persisted_page(journal, registry, symbol=symbol,
            interval=interval, after_entry_id=cursor, limit=page_size)
        pages += 1
        added += result["added"]
        existing += result["existing"]
        if result["failed_key"] is not None:
            return {"added": added, "existing": existing, "pages": pages,
                    "complete": False, "failed_key": result["failed_key"]}
        cursor = result["next_cursor"]
        if result["complete"]:
            return {"added": added, "existing": existing, "pages": pages,
                    "complete": True, "failed_key": None}
    return {"added": added, "existing": existing, "pages": pages,
            "complete": False, "failed_key": None}
