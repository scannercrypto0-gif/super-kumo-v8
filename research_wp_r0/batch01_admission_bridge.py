"""Read-only Batch 01 provenance gate for current-main frozen research plans.

This is NOT a legacy trial import, execution adapter, admission receipt or
independent custody attestation. Never marks a candidate evaluated/promoted.
"""
from .frozen_research_plan import verify_research_plan
from .strategy_definition import canonical, digest, identifier


def check_synthetic_batch_manifest(raw_plan, expected_plan_digest, manifest):
    """Return a bounded, detached, explicitly unverified synthetic inventory.

    The caller must independently retain the expected plan digest; a digest
    supplied alongside a mutable plan is not independent custody.
    """
    plan = verify_research_plan(raw_plan, expected_plan_digest)
    if type(manifest) is not dict or set(manifest) != {
        "data_class", "family_id", "protocol_digest", "dataset_digest",
        "split_digest", "baseline_digest", "candidates", "evidence_status",
    }:
        raise ValueError("Unexpected Batch 01 manifest shape")
    if manifest["data_class"] != "SYNTHETIC_TEST":
        raise ValueError("Only isolated synthetic fixtures supported")
    if manifest["evidence_status"] != "INSUFFICIENT_EVIDENCE":
        raise ValueError("Synthetic candidates cannot be promoted")
    for field in ("family_id", "protocol_digest", "dataset_digest",
                  "split_digest", "baseline_digest"):
        if manifest[field] != plan[field]:
            raise ValueError("Frozen plan provenance mismatch: " + field)
    if type(manifest["candidates"]) is not list:
        raise ValueError("Candidate inventory required")
    frozen = {r["candidate_id"]: r["strategy_digest"]
              for r in plan["candidates"]}
    if len(manifest["candidates"]) != len(frozen):
        raise ValueError("Candidate inventory differs from frozen plan")
    seen = set()
    for row in manifest["candidates"]:
        if type(row) is not dict or set(row) != {"candidate_id", "strategy_digest"}:
            raise ValueError("Unexpected candidate fields")
        cid = identifier(row["candidate_id"])
        if cid in seen or frozen.get(cid) != row["strategy_digest"]:
            raise ValueError("Unfrozen, duplicate or mismatched candidate")
        seen.add(cid)
    # Canonicalize to detach caller-owned mutable dictionaries; no result
    # acceptance or attempt ledger writes are performed here.
    canonical(manifest)
    return {
        "plan_digest": expected_plan_digest,
        "manifest_digest": digest(manifest),
        "candidate_count": len(seen),
        "data_class": "SYNTHETIC_TEST",
        "evidence_status": "INSUFFICIENT_EVIDENCE",
        "external_custody_verified": False,
        "evaluated": False,
        "admitted": False,
        "holdout_opened": False,
    }
