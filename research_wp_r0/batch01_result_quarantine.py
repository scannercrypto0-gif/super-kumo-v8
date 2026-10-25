"""Quarantine synthetic Batch 01 result claims without ledger COMPLETE writes.

This is a deterministic read-only linkage report, not evaluation or custody.
"""
from .attempt_ledger import AttemptLedger
from .batch01_admission_bridge import check_synthetic_batch_manifest
from .strategy_definition import canonical, digest, identifier


def quarantine_synthetic_result(ledger, raw_plan, expected_plan_digest,
                                manifest, claim):
    """Check a claimed result against an existing PENDING attempt.

    No results are accepted, persisted or marked COMPLETE. Caller must retain
    claim bytes/digest independently for any later research custody process.
    """
    if not isinstance(ledger, AttemptLedger):
        raise ValueError("Real Factory ledger required")
    gate = check_synthetic_batch_manifest(raw_plan, expected_plan_digest, manifest)
    if type(claim) is not dict or set(claim) != {
        "data_class", "candidate_id", "input_digest", "strategy_digest",
        "plan_digest", "manifest_digest", "result_digest", "claim_version",
    }:
        raise ValueError("Explicit result claim envelope required")
    if claim["data_class"] != "SYNTHETIC_TEST":
        raise ValueError("Historical results are not supported")
    identifier(claim["candidate_id"])
    identifier(claim["claim_version"])
    for field in ("input_digest", "strategy_digest", "plan_digest",
                  "manifest_digest", "result_digest"):
        value = claim[field]
        if type(value) is not str or len(value) != 64 or any(
                c not in "0123456789abcdef" for c in value):
            raise ValueError("Invalid result claim digest")
    if claim["plan_digest"] != gate["plan_digest"] or (
            claim["manifest_digest"] != gate["manifest_digest"]):
        raise ValueError("Result claim frozen provenance mismatch")
    matching = [row for row in manifest["candidates"]
                if row["candidate_id"] == claim["candidate_id"]]
    if len(matching) != 1 or matching[0]["strategy_digest"] != claim["strategy_digest"]:
        raise ValueError("Unfrozen result candidate/strategy")
    events, checkpoint = ledger.snapshot()
    pending = [e for e in events if e["state"] == "PENDING"
               and e["family_id"] == manifest["family_id"]
               and e["candidate_id"] == claim["candidate_id"]
               and e["input_digest"] == claim["input_digest"]
               and e["strategy_digest"] == claim["strategy_digest"]]
    if len(pending) != 1:
        raise ValueError("No uniquely bound PENDING attempt")
    canonical(claim)
    return {"claim_digest": digest(claim), "checkpoint": checkpoint,
            "candidate_id": claim["candidate_id"],
            "disposition": "QUARANTINED_NOT_EVALUATED",
            "data_class": "SYNTHETIC_TEST",
            "result_verified": False, "external_custody_verified": False,
            "ledger_complete_written": False, "holdout_opened": False}
