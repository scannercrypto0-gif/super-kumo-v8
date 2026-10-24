"""Research-only, read-only integrity checks for frozen Factory candidate families."""
from .attempt_ledger import AttemptLedger
from .strategy_definition import canonical, digest, identifier, load_json

def frozen_commitment(family_id, candidates):
    """Commit all candidate IDs and StrategyDefinition digests before attempts."""
    identifier(family_id)
    if not 1 <= len(candidates) <= 256:
        raise ValueError("Bounded candidate family required")
    seen = set()
    records = []
    for cid, definition in candidates:
        identifier(cid)
        if cid in seen:
            raise ValueError("Duplicate candidate")
        seen.add(cid)
        records.append({"candidate_id": cid, "strategy_digest": definition.digest})
    plan = {"schema_version": "1", "family_id": family_id, "candidates": records}
    return canonical(plan), digest(plan)

def reconcile_plan(raw_plan, expected_digest, ledger):
    """Verify plan and real ledger; never assert completed evaluation."""
    plan = load_json(raw_plan.decode("utf-8"))
    if canonical(plan) != raw_plan or digest(plan) != expected_digest:
        raise ValueError("Frozen plan mismatch")
    if plan.get("schema_version") != "1":
        raise ValueError("Unknown plan version")
    allowed = {x["candidate_id"]: x["strategy_digest"] for x in plan["candidates"]}
    if len(allowed) != len(plan["candidates"]):
        raise ValueError("Duplicate candidate")
    if not isinstance(ledger, AttemptLedger):
        raise ValueError("Factory AttemptLedger required")
    events, checkpoint = ledger.snapshot()
    states = {}
    for event in events:
        if event["family_id"] != plan["family_id"]:
            continue
        cid = event["candidate_id"]
        if cid not in allowed:
            raise ValueError("Unknown candidate")
        if event.get("strategy_digest") not in (None, allowed[cid]):
            raise ValueError("Strategy digest mismatch")
        if event["state"] != "INPUTS":
            states[cid] = event["state"]
    return {"checkpoint": checkpoint, "missing": sorted(set(allowed) - set(states)),
            "pending": sorted(cid for cid in states if states[cid] == "PENDING"),
            "evaluation_status": "NOT_EVALUATED"}
