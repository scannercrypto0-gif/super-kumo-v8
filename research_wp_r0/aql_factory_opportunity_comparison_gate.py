"""Factory #250: fail-closed, descriptive opportunity and comparison gate.

Never upgrades retrospective source integrity, TEST_ONLY candidate origin or
self-reported opportunity counts to historical PIT or scientific efficacy.
No price engine, no private source access, no holdout inspection.
"""
from __future__ import annotations

import hashlib
import json
from collections import Counter
from decimal import Decimal, InvalidOperation

SCHEMA = "aql.factory.opportunity-comparison-plan.v1"
REPORT = "aql.factory.opportunity-comparison-report.v1"
STATES = ("ELIGIBLE", "INELIGIBLE", "UNSCANNED", "REJECTED", "UNKNOWN", "MISSING")
ARMS = ("BASE", "SHADOW")


class OpportunityGateError(ValueError):
    pass


def _require(ok, code):
    if not ok:
        raise OpportunityGateError(code)


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                     ensure_ascii=True, allow_nan=False).encode()).hexdigest()


def _pin(value):
    return isinstance(value, str) and len(value) == 64 and all(c in "0123456789abcdef" for c in value)


def _money(value, field):
    _require(type(value) is str, "COST_TYPE_" + field)
    try:
        n = Decimal(value)
    except (InvalidOperation, ValueError):
        raise OpportunityGateError("COST_INVALID_" + field)
    _require(n.is_finite() and Decimal(0) <= n <= Decimal(1000), "COST_RANGE_" + field)
    return n


def assess_opportunity_comparison(packet):
    """Validate a frozen plan and emit only non-promotional descriptive evidence.

    The optional universe evidence is an *externally supplied complete inventory*,
    never inferred from candidate outcomes or OHLCV rows. Missing inventory stays
    UNKNOWN; no fabricated zero denominator or BASE/SHADOW result.
    """
    _require(type(packet) is dict and packet.get("schema") == SCHEMA, "SCHEMA")
    _require(packet.get("holdout") == "SEALED_UNOPENED", "HOLDOUT")
    _require(packet.get("execution_authority") == "NONE", "AUTHORITY")
    _require(packet.get("candidate_origin") == "INDEPENDENT_TEST_ONLY_RESEARCH_SEED",
             "CANDIDATE_ORIGIN")
    _require(packet.get("historical_pit") == "NOT_ATTESTED", "FALSE_PIT")
    _require(packet.get("historical_preregistration") is False, "FALSE_PREREGISTRATION")
    _require(packet.get("comparison_plan_frozen_before_evaluation") is True,
             "PLAN_NOT_FROZEN")
    _require(packet.get("comparison_scope") == "DEVELOPMENT_ONLY", "COMPARISON_SCOPE")
    _require(packet.get("embargo_ms") is not None
             and type(packet["embargo_ms"]) is int
             and packet["embargo_ms"] >= 259200000, "EMBARGO")
    _require(type(packet.get("development_end_ms")) is int
             and type(packet.get("holdout_start_ms")) is int
             and packet["development_end_ms"] + packet["embargo_ms"] <= packet["holdout_start_ms"],
             "WINDOW_LEAKAGE")
    _require(type(packet.get("source_pins")) is dict
             and set(packet["source_pins"]) == {"archive_sha256", "member_sha256",
                                                  "checksum_sha256", "core_price_query_sha256"}
             and all(_pin(x) for x in packet["source_pins"].values()), "SOURCE_PINS")
    _require(_pin(packet.get("candidate_generation_sha256"))
             and _pin(packet.get("precalculation_plan_sha256")), "PLAN_PINS")
    trials = packet.get("trials")
    _require(type(trials) is list and len(trials) == 53, "TRIAL_DENOMINATOR")
    seen = set()
    for trial in trials:
        _require(type(trial) is dict and set(trial) == {"attempt_id", "family_id", "state"},
                 "TRIAL_SHAPE")
        aid = trial["attempt_id"]
        _require(type(aid) is str and bool(aid) and aid not in seen, "TRIAL_DUPLICATE")
        seen.add(aid)
        _require(type(trial["family_id"]) is str and bool(trial["family_id"])
                 and trial["state"] in ("PROPOSED", "INVALID", "DUPLICATE", "FAILED",
                                       "REJECTED", "UNKNOWN", "BUDGET_EXHAUSTED"),
                 "TRIAL_STATUS")
    _require(type(packet.get("selection_multiplicity")) is dict
             and set(packet["selection_multiplicity"]) ==
             {"attempts_examined", "families_examined", "selection_policy", "adjustment_status"},
             "MULTIPLICITY_SHAPE")
    mult = packet["selection_multiplicity"]
    _require(mult["attempts_examined"] == 53
             and type(mult["families_examined"]) is int
             and mult["families_examined"] == len({t["family_id"] for t in trials})
             and mult["selection_policy"] == "FROZEN_NO_OUTCOME_RETUNING"
             and mult["adjustment_status"] == "NOT_ESTIMATED",
             "MULTIPLICITY_FALSE_CERTIFICATION")
    costs = packet.get("modeled_costs_bps")
    _require(type(costs) is dict and set(costs) ==
             {"fee_entry", "fee_exit", "spread_entry", "spread_exit",
              "slippage_entry", "slippage_exit", "funding"}, "COST_SHAPE")
    parsed = {k: _money(v, k) for k, v in costs.items()}
    scenarios = packet.get("cost_scenarios_bps")
    _require(type(scenarios) is list and len(scenarios) >= 2, "COST_SENSITIVITY")
    scenario_names = set()
    for scenario in scenarios:
        _require(type(scenario) is dict and set(scenario) == {"name", "total_round_trip_bps"},
                 "SCENARIO_SHAPE")
        name = scenario["name"]
        _require(type(name) is str and name and name not in scenario_names,
                 "SCENARIO_DUPLICATE")
        scenario_names.add(name)
        _money(scenario["total_round_trip_bps"], "scenario")
    _require("BASE_ASSUMPTION" in scenario_names and "HIGHER_COST" in scenario_names,
             "SENSITIVITY_MISSING")
    base_total = sum(parsed.values(), Decimal(0))
    _require(any(s["name"] == "BASE_ASSUMPTION"
                 and _money(s["total_round_trip_bps"], "base") == base_total
                 for s in scenarios), "BASE_COST_MISMATCH")
    _require(any(s["name"] == "HIGHER_COST"
                 and _money(s["total_round_trip_bps"], "high") > base_total
                 for s in scenarios), "HIGH_COST_NOT_HIGHER")

    inventory = packet.get("universe_inventory")
    counts = None
    arm_count = None
    if inventory is not None:
        _require(type(inventory) is dict
                 and set(inventory) == {"scope", "coverage", "source_manifest_sha256",
                                        "opportunities"}, "INVENTORY_SHAPE")
        _require(inventory["scope"] == "EXPLICIT_SINGLE_SYMBOL_DEVELOPMENT"
                 and inventory["coverage"] == "SUPPLIED_NOT_INDEPENDENTLY_ATTESTED"
                 and _pin(inventory["source_manifest_sha256"]), "INVENTORY_AUTHORITY")
        items = inventory["opportunities"]
        _require(type(items) is list and len(items) > 0, "INVENTORY_EMPTY")
        counts = Counter({s: 0 for s in STATES})
        ids, slots = set(), set()
        for item in items:
            _require(type(item) is dict and set(item) ==
                     {"opportunity_id", "bar_open_ms", "status", "reason",
                      "base_status", "shadow_status"}, "OPPORTUNITY_SHAPE")
            oid = item["opportunity_id"]
            t = item["bar_open_ms"]
            _require(type(oid) is str and oid and oid not in ids, "OPPORTUNITY_DUPLICATE")
            ids.add(oid)
            _require(type(t) is int and t < packet["development_end_ms"]
                     and (oid, t) not in slots, "OPPORTUNITY_CLOCK")
            slots.add((oid, t))
            state = item["status"]
            _require(state in STATES and type(item["reason"]) is str
                     and bool(item["reason"]), "OPPORTUNITY_STATE")
            _require(item["base_status"] in ("NOT_EVALUATED", "UNKNOWN")
                     and item["shadow_status"] in ("NOT_EVALUATED", "UNKNOWN"),
                     "PREMATURE_ARM_RESULT")
            counts[state] += 1
        _require(sum(counts.values()) == len(items), "DENOMINATOR_CONSERVATION")
        arm_count = len(items) * 2

    result = {
        "schema": REPORT,
        "input_sha256": _digest(packet),
        "source_pins": packet["source_pins"],
        "trial_attempts": 53,
        "unique_families": mult["families_examined"],
        "historical_preregistration": "NOT_ESTABLISHED",
        "multiplicity_adjustment": "NOT_ESTIMATED",
        "universe_denominator": None if counts is None else sum(counts.values()),
        "universe_status_counts": None if counts is None else dict(counts),
        "paired_arm_slots": arm_count,
        "independent_market_opportunity_denominator": None,
        "base_shadow_comparison": None,
        "modeled_cost_scenarios_bps": scenarios,
        "modeled_returns_recomputed": False,
        "independent_venue_provenance": "NOT_ATTESTED",
        "historical_pit": "NOT_ATTESTED",
        "retrospective_evidence": "DESCRIPTIVE_ONLY",
        "scientific_result": "INSUFFICIENT_EVIDENCE",
        "holdout": "SEALED_UNOPENED",
        "trading_authority": "NONE",
    }
    result["report_sha256"] = _digest(result)
    return result
