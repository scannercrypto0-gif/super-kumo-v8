"""Full research protocol commitment, independent of evaluation execution.

A commitment is NOT a trusted custody receipt: preserve the digest outside
the authority that can modify the manifest or attempt ledger.
"""
import re

from .strategy_definition import canonical, digest, identifier, load_json

_HEX = re.compile(r"[0-9a-f]{64}\Z")


def _hash(value):
    if type(value) is not str or _HEX.fullmatch(value) is None:
        raise ValueError("Expected SHA-256 hex digest")


def commit_research_plan(family_id, candidates, *, protocol_digest,
                         dataset_digest, split_digest, metrics,
                         selection_rule, cost_model, baseline_digest):
    """Freeze candidates, PIT dataset/split, costs, metrics and selection rules."""
    identifier(family_id)
    if type(candidates) not in (tuple, list) or not 1 <= len(candidates) <= 256:
        raise ValueError("Bounded candidate inventory required")
    ids, records = set(), []
    for candidate_id, strategy_digest in candidates:
        identifier(candidate_id)
        _hash(strategy_digest)
        if candidate_id in ids:
            raise ValueError("Duplicate candidate")
        ids.add(candidate_id)
        records.append({"candidate_id": candidate_id,
                        "strategy_digest": strategy_digest})
    for item in (protocol_digest, dataset_digest, split_digest, baseline_digest):
        _hash(item)
    if type(metrics) is not list or not metrics or len(metrics) > 64 or (
        any(type(m) is not str or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_.-]{0,63}", m)
            for m in metrics) or len(set(metrics)) != len(metrics)
    ):
        raise ValueError("Predeclared unique metrics required")
    if type(selection_rule) is not dict or not selection_rule:
        raise ValueError("Explicit selection rule required")
    if type(cost_model) is not dict or not cost_model:
        raise ValueError("Explicit cost model required")
    plan = {"schema_version": "research-plan-1", "family_id": family_id,
            "candidates": records, "protocol_digest": protocol_digest,
            "dataset_digest": dataset_digest, "split_digest": split_digest,
            "baseline_digest": baseline_digest, "metrics": metrics,
            "selection_rule": selection_rule, "cost_model": cost_model}
    raw = canonical(plan)
    if len(raw) > 100000:
        raise ValueError("Research plan exceeds size bound")
    return raw, digest(plan)


def verify_research_plan(raw, expected_digest):
    """Reject any changed plan or noncanonical encoding; never imply EVALUATED."""
    if type(raw) is not bytes or len(raw) > 100000:
        raise ValueError("Bounded plan bytes required")
    try:
        plan = load_json(raw.decode("utf-8"))
    except UnicodeDecodeError as exc:
        raise ValueError("UTF-8 required") from exc
    if type(plan) is not dict or set(plan) != {
        "schema_version", "family_id", "candidates", "protocol_digest",
        "dataset_digest", "split_digest", "baseline_digest", "metrics",
        "selection_rule", "cost_model"
    }:
        raise ValueError("Unknown research plan shape")
    if plan["schema_version"] != "research-plan-1":
        raise ValueError("Unsupported research plan")
    rebuilt, computed = commit_research_plan(
        plan["family_id"],
        [(r["candidate_id"], r["strategy_digest"]) for r in plan["candidates"]],
        protocol_digest=plan["protocol_digest"], dataset_digest=plan["dataset_digest"],
        split_digest=plan["split_digest"], baseline_digest=plan["baseline_digest"],
        metrics=plan["metrics"], selection_rule=plan["selection_rule"],
        cost_model=plan["cost_model"])
    if raw != rebuilt or computed != expected_digest:
        raise ValueError("Research plan commitment mismatch")
    return plan
