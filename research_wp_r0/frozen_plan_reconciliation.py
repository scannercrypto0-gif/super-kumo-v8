"""Research-only, read-only integrity checks for frozen Factory candidate families."""
from .attempt_ledger import AttemptLedger
from .strategy_definition import StrategyDefinition, canonical, digest, identifier, load_json

def frozen_commitment(family_id, candidates):
    """Commit all candidate IDs and StrategyDefinition digests before attempts."""
    identifier(family_id)
    if type(candidates) not in (list, tuple) or not 1 <= len(candidates) <= 256:
        raise ValueError("Bounded candidate family required")
    seen = set()
    records = []
    for cid, definition in candidates:
        identifier(cid)
        if cid in seen or not isinstance(definition, StrategyDefinition):
            raise ValueError("Duplicate candidate or unvalidated strategy")
        seen.add(cid)
        records.append({"candidate_id": cid, "strategy_digest": definition.digest})
    plan = {"schema_version": "1", "family_id": family_id, "candidates": records}
    return canonical(plan), digest(plan)

def reconcile_plan(raw_plan, expected_digest, ledger):
    """Verify plan and real ledger; never assert completed evaluation."""
    plan = load_json(raw_plan.decode("utf-8"))
    if canonical(plan) != raw_plan or digest(plan) != expected_digest:
        raise ValueError("Frozen plan mismatch")
    if type(plan) is not dict or set(plan) != {"schema_version", "family_id", "candidates"}:\n        raise ValueError("Malformed frozen plan")\n    if plan.get("schema_version") != "1":
        raise ValueError("Unknown plan version")
    identifier(plan["family_id"])
    if not isinstance(plan.get("candidates"), list) or not 1 <= len(plan["candidates"]) <= 256:
        raise ValueError("Invalid frozen candidate list")
    allowed = {}
    for item in plan["candidates"]:
        if type(item) is not dict or set(item) != {"candidate_id", "strategy_digest"}:
            raise ValueError("Malformed frozen candidate")
        cid = identifier(item["candidate_id"])
        sd = item["strategy_digest"]
        if type(sd) is not str or len(sd) != 64 or any(ch not in "0123456789abcdef" for ch in sd):
            raise ValueError("Malformed strategy digest")
        if cid in allowed:
            raise ValueError("Duplicate candidate")
        allowed[cid] = sd
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
        if event.get("strategy_digest") != allowed[cid]:
            raise ValueError("Strategy digest mismatch")
        if event["state"] != "INPUTS":
            states[cid] = event["state"]
    return {"checkpoint": checkpoint, "missing": sorted(set(allowed) - set(states)),
            "pending": sorted(cid for cid in states if states[cid] == "PENDING"),
            "evaluation_status": "NOT_EVALUATED"}
