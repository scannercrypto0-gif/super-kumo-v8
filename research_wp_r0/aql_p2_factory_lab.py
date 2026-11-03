"""Factory P2 development-only paired descriptive consumer.

Consumes Core aql.p2.core.paired-schedule.v1 without importing an unmerged PR.
No trade simulation, realized PnL, strategy uplift, PIT or holdout access.
"""
from __future__ import annotations

from collections import Counter
from hashlib import sha256
import json
import math

HORIZONS = (4, 24, 72)
AVAILABILITY = {"COMPLETE", "CENSORED", "UNKNOWN"}
DISPOSITIONS = {"NO_SIGNAL", "REJECTED", "TRIGGERED", "UNKNOWN"}
HEX = set("0123456789abcdef")


class LabContractError(ValueError):
    pass


def require(ok, code):
    if not ok:
        raise LabContractError(code)


def digest(obj):
    return sha256(json.dumps(obj, sort_keys=True, separators=(",", ":"),
                             ensure_ascii=True, allow_nan=False).encode("utf-8")).hexdigest()


def hash_ok(s):
    return isinstance(s, str) and len(s) == 64 and set(s) <= HEX


def integer(value):
    return type(value) is int


def validate_schedule(schedule):
    require(isinstance(schedule, dict), "BAD_SCHEDULE")
    require(schedule.get("schema") == "aql.p2.core.paired-schedule.v1", "BAD_SCHEMA")
    require(schedule.get("evidence_class") == "RETROSPECTIVE_NON_PIT", "PIT_CLAIM")
    require(schedule.get("holdout_status") == "SEALED_UNOPENED", "HOLDOUT_OPEN")
    require(schedule.get("outcome_evaluation") == "NOT_PERFORMED", "PRECOMPUTED_OUTCOMES")
    require(schedule.get("execution_status") == "NOT_OBSERVED", "EXECUTION_CLAIM")
    require(type(schedule.get("test_only")) is bool, "MISSING_TEST_FLAG")
    pin = schedule.get("artifact_sha256")
    require(hash_ok(pin), "BAD_SCHEDULE_DIGEST")
    payload = {k: v for k, v in schedule.items() if k != "artifact_sha256"}
    require(digest(payload) == pin, "SCHEDULE_DIGEST_MISMATCH")
    protocol = schedule.get("protocol")
    source = schedule.get("source")
    require(isinstance(protocol, dict) and isinstance(source, dict), "BAD_LINEAGE")
    require(hash_ok(protocol.get("protocol_sha256")), "BAD_PROTOCOL_PIN")
    require(hash_ok(source.get("source_package_sha256")), "BAD_SOURCE_PIN")
    require(integer(protocol.get("embargo_ms")) and
            protocol["embargo_ms"] >= 259200000, "EMBARGO_TOO_SHORT")
    require(integer(protocol.get("train_end_exclusive_ms")) and
            integer(protocol.get("holdout_start_ms")) and
            integer(protocol.get("holdout_end_exclusive_ms")) and
            protocol["train_end_exclusive_ms"] + protocol["embargo_ms"] <=
            protocol["holdout_start_ms"] < protocol["holdout_end_exclusive_ms"],
            "TRAIN_HOLDOUT_LEAKAGE")
    pairs = schedule.get("pairs")
    require(isinstance(pairs, list) and len(pairs) > 0, "EMPTY_PAIRS")
    require(integer(schedule.get("scheduled_total")) and
            schedule["scheduled_total"] == len(pairs), "DENOMINATOR_MISMATCH")
    ids = set()
    for pair in pairs:
        require(isinstance(pair, dict), "BAD_PAIR")
        pid = pair.get("pair_id")
        require(hash_ok(pid) and pid not in ids, "DUPLICATE_OR_BAD_PAIR_ID")
        ids.add(pid)
        opportunity = pair.get("opportunity")
        require(isinstance(opportunity, dict), "BAD_OPPORTUNITY")
        require(opportunity.get("disposition") in DISPOSITIONS, "BAD_DISPOSITION")
        direction = opportunity.get("direction")
        direction_ref = opportunity.get("direction_evidence_ref")
        require(direction in (None, "LONG", "SHORT"), "BAD_ORIGINAL_DIRECTION")
        require((direction is None and direction_ref is None) or
                (direction is not None and isinstance(direction_ref, str)
                 and bool(direction_ref.strip())), "DIRECTION_WITHOUT_EVIDENCE")
        regime = opportunity.get("regime")
        regime_pin = opportunity.get("regime_source_sha256")
        require((regime is None and regime_pin is None) or
                (isinstance(regime, str) and bool(regime.strip())
                 and hash_ok(regime_pin)), "REGIME_WITHOUT_SOURCE")
        require(opportunity.get("evidence_class") == "RETROSPECTIVE_NON_PIT", "PIT_OPPORTUNITY")
        require(opportunity.get("trial_id") == protocol.get("trial_id") and
                opportunity.get("source_id") == source.get("source_id") and
                opportunity.get("source_package_sha256") == source.get("source_package_sha256"),
                "CROSS_SOURCE_PAIR")
        cutoff = opportunity.get("decision_cutoff_ms")
        require(integer(cutoff) and cutoff >= 0 and cutoff < protocol["train_end_exclusive_ms"],
                "HOLDOUT_OPPORTUNITY")
        require(integer(opportunity.get("decision_ms")) and
                cutoff <= opportunity["decision_ms"] < protocol["train_end_exclusive_ms"],
                "BAD_DECISION_TIME")
        require(pid == digest(dict(protocol_sha256=protocol["protocol_sha256"],
                                   trial_id=protocol["trial_id"],
                                   opportunity_id=opportunity.get("opportunity_id"))),
                "PAIR_ID_MISMATCH")
        arms = pair.get("arms")
        require(isinstance(arms, list) and len(arms) == 2 and
                {a.get("arm") for a in arms if isinstance(a, dict)} == {"BASE", "SHADOW"},
                "UNPAIRED_ARMS")
        for arm in arms:
            require(arm.get("definition_sha256") ==
                    protocol.get("base_definition_sha256" if arm["arm"] == "BASE"
                                 else "shadow_definition_sha256"), "ARM_DEFINITION_MISMATCH")
    return {p["pair_id"]: p for p in pairs}


def build_lab(schedule, observations, *, test_only=True):
    """One observation per pair/arm/horizon, full denominator and honest missingness.

    Observations are descriptive horizon coverage, not evidence of executable trades.
    Both arms use the same source-backed market window; absent genuine direction
    no directional statistic is computed. No effect size/alpha is emitted.
    """
    pairs = validate_schedule(schedule)
    require(test_only is True and schedule["test_only"] is True,
            "REAL_EVALUATION_NOT_AUTHORIZED")
    require(isinstance(observations, list), "BAD_OBSERVATIONS")
    slots = {}
    for row in observations:
        require(isinstance(row, dict), "BAD_OBSERVATION")
        pid, arm, horizon = row.get("pair_id"), row.get("arm"), row.get("horizon_hours")
        require(pid in pairs and arm in ("BASE", "SHADOW") and
                integer(horizon) and horizon in HORIZONS, "UNKNOWN_SLOT")
        key = (pid, arm, horizon)
        require(key not in slots, "DUPLICATE_SLOT")
        status = row.get("availability")
        require(status in AVAILABILITY, "BAD_AVAILABILITY")
        reason = row.get("availability_reason")
        metrics = row.get("market_metrics")
        if status == "COMPLETE":
            require(reason is None and isinstance(metrics, dict), "BAD_COMPLETE")
            require(set(metrics) == {"reference_price", "observed_high", "observed_low"},
                    "BAD_METRIC_SHAPE")
            require(all(type(v) in (float, int) and math.isfinite(v)
                        for v in metrics.values()), "NONFINITE_METRIC")
            require(metrics["reference_price"] > 0 and
                    metrics["observed_high"] >= metrics["observed_low"] > 0,
                    "BAD_MARKET_RANGE")
        else:
            require(isinstance(reason, str) and bool(reason.strip()) and metrics is None,
                    "UNVERIFIED_MISSINGNESS")
        require(row.get("directional_metrics") is None and
                row.get("execution_status") == "NOT_OBSERVED",
                "UNVERIFIED_EXECUTION_OR_DIRECTION")
        slots[key] = row
    expected = {(pid, arm, h) for pid in pairs for arm in ("BASE", "SHADOW")
                for h in HORIZONS}
    require(set(slots) == expected, "INCOMPLETE_DENOMINATOR")
    # Paired source windows must agree across arms; reject differing coverage/market
    # observations instead of manufacturing a strategy difference.
    coverage = {}
    for horizon in HORIZONS:
        counts = Counter()
        for pid in pairs:
            base, shadow = (slots[(pid, arm, horizon)] for arm in ("BASE", "SHADOW"))
            require(all(base.get(k) == shadow.get(k) for k in
                        ("availability", "availability_reason", "market_metrics")),
                    "UNPAIRED_SOURCE_WINDOW")
            counts[base["availability"]] += 1
        coverage[str(horizon)] = {s: counts[s] for s in ("COMPLETE", "CENSORED", "UNKNOWN")}
    artifact = {
        "schema": "aql.p2.factory.paired-lab.v1",
        "test_only": True,
        "scope": "RETROSPECTIVE_NON_PIT_DESCRIPTIVE",
        "source_schedule_sha256": schedule["artifact_sha256"],
        "scheduled_opportunities": len(pairs),
        "observation_slots": len(slots),
        "disposition_counts": dict(sorted(Counter(
            p["opportunity"]["disposition"] for p in pairs.values()).items())),
        "market_coverage_by_horizon": coverage,
        "paired_strategy_effect": "NOT_EVALUABLE_NO_VERIFIED_ARM_OUTCOMES",
        "fills_pnl_alpha": "NOT_COMPUTED",
        "holdout_status": "SEALED_UNOPENED",
    }
    artifact["artifact_sha256"] = digest(artifact)
    return artifact
