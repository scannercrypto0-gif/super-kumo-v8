"""Factory #254: isolated same-original-source Core lab-result → TEST_ONLY paper decision.

This is an additive read-only seam for the final owner-approved one-batch gate.
Core #253 owns price/indicator/trigger computation; Factory never recomputes
the 106 accepted historical studies or invents operational Scanner SELECTED.
Core schema below is a *provisional handshake*, not evidence Core has delivered
it. The adapter cannot run until a genuine Core-produced receipt is supplied.
"""
from __future__ import annotations

from dataclasses import asdict

from research_wp_r0.aql_factory_authentic_research_admission import (
    _check_seal, _digest, _hash,
)
from research_wp_r0.aql_factory_unified_backbone_v1 import (
    SOURCE_SCHEMA, checked, freeze,
)
from research_wp_r0.indicator_library_v2 import IndicatorRegistryV2
from research_wp_r0.strategy_definition import StrategyDefinition
from src.aql.observation.contracts import PaperIntent
from src.aql.observation.positions import PositionLedger

CORE_LAB_SCHEMA = "aql.core.offline-lab-test-strategy.v1"
FACTORY_LAB_SCHEMA = "aql.factory.same-original-lab-assessment.v1"
FACTORY_DECISION_SCHEMA = "aql.factory.same-original-lab-paper-decision.v1"
STATES = ("ENTRY_TRIGGERED", "EXIT_TRIGGERED", "NO_SIGNAL", "UNKNOWN")
MAX_BARS = 5_000
POLICY = "FACTORY254_ISOLATED_RESEARCH_TEST_ONLY_REJECT_OR_WAIT_V1"


class LabHandoffError(ValueError):
    pass


def require(ok, code):
    if not ok:
        raise LabHandoffError("FACTORY_254_LAB_" + code)


def admit_core_lab_calculation(source, result):
    """Validate evidence/denominators from actual Core-owned calculation.

    Source receipt must already be bound to original Core #253 committed RAW
    warehouse and source-specific read-only query. This consumer deliberately
    avoids trusting independent self-declared source or PIT booleans.
    """
    try:
        checked(source, "artifact_sha256")
        checked(result, "evaluation_sha256")
    except (TypeError, ValueError, KeyError) as exc:
        raise LabHandoffError("FACTORY_254_LAB_SEAL") from exc
    require(source.get("schema") == SOURCE_SCHEMA
            and source.get("raw_warehouse_query") ==
                "CONNECTED_PINNED_CORE_253_RAW_WAREHOUSE"
            and source.get("core_query_consumer") ==
                "CONNECTED_READ_ONLY_CORE_CUSTODY"
            and source.get("coverage") == "COMPLETE"
            and source.get("missing_bar_opens") == []
            and source.get("holdout") == "SEALED_UNOPENED"
            and source.get("trading_authority") == "NONE"
            and source.get("source_eligible_for_historical_pit") is False,
            "SOURCE_NOT_REAL_COMMITTED_OR_FALSE_AUTHORITY")
    require(result.get("schema") == CORE_LAB_SCHEMA
            and result.get("research_lane") == "OFFLINE_LAB_TEST_STRATEGY"
            and result.get("evidence_class") == "RETROSPECTIVE_NON_PIT"
            and result.get("test_only") is True
            and result.get("operational_scanner_status") == "UNKNOWN"
            and result.get("historical_known_at_ms") is None
            and result.get("historical_pit") == "NOT_ATTESTED"
            and result.get("scientific_result") == "INSUFFICIENT_EVIDENCE"
            and result.get("trading_authority") == "NONE"
            and result.get("real_paper_activation") == "DISABLED"
            and result.get("holdout") == "SEALED_UNOPENED",
            "CORE_LAB_AUTHORITY_OR_MODE")
    pins = (
        ("dataset_id", "dataset_id"),
        ("version", "version"),
        ("source_zip_sha256", "source_bytes_sha256"),
        ("manifest_integrity_sha256", "manifest_integrity_sha256"),
        ("warehouse_receipt_sha256", "core_253_warehouse_receipt_sha256"),
        ("core_price_query_sha256", "core_price_query_sha256"),
        ("core_253_query_sha256", "core_253_warehouse_query_sha256"),
        ("decision_cutoff_ms", "cutoff_ms"),
    )
    require(all(result.get(k) == source.get(v) for k,v in pins)
            and _hash(result.get("source_zip_sha256"))
            and _hash(result.get("manifest_integrity_sha256")),
            "CORE_LAB_SOURCE_PIN_MISMATCH")
    definition = result.get("strategy_definition")
    try:
        strategy = StrategyDefinition.from_dict(
            definition, registry=IndicatorRegistryV2())
    except (KeyError, TypeError, ValueError) as exc:
        raise LabHandoffError("FACTORY_254_LAB_DEFINITION_INVALID") from exc
    require(strategy.digest == result.get("strategy_digest")
            and result.get("strategy_id") == strategy.spec["strategy_id"]
            and result.get("strategy_version") ==
                strategy.spec["strategy_version"]
            and strategy.spec["scope"] == "RESEARCH_ONLY",
            "STRATEGY_IDENTITY")
    rows = result.get("decisions")
    count = result.get("bar_count")
    required = source.get("bar_count_required")
    require(type(count) is int and 2 <= count <= MAX_BARS
            and count == source.get("bar_count_available") == required
            and type(result.get("width_ms")) is int
            and result["width_ms"] == 900_000
            and type(result.get("source_first_bar_open_ms")) is int
            and type(rows) is list and len(rows) == count-1
            and type(result.get("decision_slots")) is int
            and result["decision_slots"] == len(rows),
            "BAR_OR_DECISION_DENOMINATOR")
    census = result.get("decision_counts")
    require(type(census) is dict and set(census) == set(STATES)
            and all(type(v) is int and v >= 0 for v in census.values())
            and sum(census.values()) == len(rows),
            "CENSUS")
    actual = {k: 0 for k in STATES}
    first = result["source_first_bar_open_ms"]
    require(first >= 0 and first % 900_000 == 0, "FIRST_BAR_GRID")
    for i, row in enumerate(rows):
        require(type(row) is dict
                and set(row) == {"bar_open_ms", "state", "indicator_ready"}
                and type(row["bar_open_ms"]) is int
                and row["bar_open_ms"] == first + i*900_000
                and row["state"] in STATES
                and type(row["indicator_ready"]) is bool
                and (row["indicator_ready"] or row["state"] == "UNKNOWN"),
                "CORE_COMPUTED_DECISION_GRID")
        actual[row["state"]] += 1
    require(actual == census, "DECISION_CENSUS_MISMATCH")
    require(result.get("attempt_denominator") == 1
            and result.get("attempt_id") ==
                _digest({"dataset_id":source["dataset_id"],
                         "source_sha256":source["source_bytes_sha256"],
                         "strategy_digest":strategy.digest,
                         "cutoff_ms":source["cutoff_ms"],
                         "research_lane":"OFFLINE_LAB_TEST_STRATEGY"})
            and result.get("independent_market_opportunity_denominator") is None
            and result.get("base_shadow_results") is None,
            "EXPERIMENT_ATTEMPT_IDENTITY")
    out = {
        "schema": FACTORY_LAB_SCHEMA,
        "source_receipt_sha256": source["artifact_sha256"],
        "core_lab_evaluation_sha256": result["evaluation_sha256"],
        "dataset_id": source["dataset_id"],
        "version": source["version"],
        "source_zip_sha256": source["source_bytes_sha256"],
        "core_warehouse_receipt_sha256":
            source["core_253_warehouse_receipt_sha256"],
        "core_price_query_sha256": source["core_price_query_sha256"],
        "core_253_query_sha256": source["core_253_warehouse_query_sha256"],
        "cutoff_ms": source["cutoff_ms"],
        "strategy_id": strategy.spec["strategy_id"],
        "strategy_version": strategy.spec["strategy_version"],
        "strategy_digest": strategy.digest,
        "attempt_id": result["attempt_id"],
        "attempt_denominator": 1,
        "bar_count": count,
        "decision_slots": count - 1,
        "decision_counts": census,
        "decision_grid_sha256": _digest(rows),
        "computed_indicators_recalculated_by_factory": False,
        "source_labeled_retro_non_pit": True,
        "operational_scanner_status": "UNKNOWN",
        "research_test_only": True,
        "historical_known_at_ms": None,
        "independent_market_opportunity_denominator": None,
        "base_shadow_results": None,
        "scientific_result": "INSUFFICIENT_EVIDENCE",
        "holdout": "SEALED_UNOPENED",
        "trading_authority": "NONE",
    }
    return freeze(out)


def isolate_test_only_paper_decision(lab, policy_id=POLICY):
    """One deterministic research-only consumer. No orders, no PAPER activation.

    Reject test candidates with observed triggered rules (no approval/PIT);
    WAIT if all decisions unknown/no signal. Never ACCEPT or label operational
    Scanner as SELECTED. Existing main PaperIntent/PositionLedger reused.
    """
    try:
        checked(lab, "artifact_sha256")
    except (TypeError, ValueError, KeyError) as exc:
        raise LabHandoffError("FACTORY_254_LAB_PAPER_PARENT_SEAL") from exc
    require(lab.get("schema") == FACTORY_LAB_SCHEMA
            and lab.get("operational_scanner_status") == "UNKNOWN"
            and lab.get("research_test_only") is True
            and lab.get("historical_known_at_ms") is None
            and lab.get("scientific_result") == "INSUFFICIENT_EVIDENCE"
            and lab.get("trading_authority") == "NONE"
            and lab.get("attempt_denominator") == 1
            and type(policy_id) is str and policy_id == POLICY,
            "PAPER_AUTHORITY_OR_POLICY")
    c = lab.get("decision_counts")
    require(type(c) is dict and set(c) == set(STATES)
            and sum(c.values()) == lab.get("decision_slots"),
            "PAPER_LAB_DENOMINATOR")
    has_rule_signal = c["ENTRY_TRIGGERED"] + c["EXIT_TRIGGERED"] > 0
    decision = "REJECT" if has_rule_signal else "WAIT"
    delivery_id = _digest({
        "lab_sha256":lab["artifact_sha256"],
        "strategy_digest":lab["strategy_digest"],
        "policy_id":policy_id,
        "source_sha256":lab["source_zip_sha256"],
        "cutoff_ms":lab["cutoff_ms"],
    })
    intent = (asdict(PaperIntent(lab["artifact_sha256"],
                                 delivery_id, "declined"))
              if decision == "REJECT" else None)
    ledger = PositionLedger()
    require(not ledger.events and not ledger.positions, "PAPER_NOT_ISOLATED")
    out = {
        "schema": FACTORY_DECISION_SCHEMA,
        "lab_receipt_sha256": lab["artifact_sha256"],
        "source_zip_sha256": lab["source_zip_sha256"],
        "strategy_id": lab["strategy_id"],
        "strategy_version": lab["strategy_version"],
        "strategy_digest": lab["strategy_digest"],
        "attempt_id": lab["attempt_id"],
        "decision_policy_id": policy_id,
        "delivery_id": delivery_id,
        "decision": decision,
        "decision_owner": "FACTORY254_ISOLATED_RESEARCH_CONSUMER",
        "decision_reason": ("RULE_COMPUTED_RESEARCH_ONLY_NO_PIT_APPROVAL"
                            if has_rule_signal else
                            "NO_ACTIONABLE_RESEARCH_RULE_SIGNAL"),
        "main_paper_intent_interface": intent,
        "operational_scanner_status": "UNKNOWN",
        "work235_actual_route": "NOT_CONNECTED_15M_UNSUPPORTED",
        "paper_positions": 0,
        "paper_position_events": 0,
        "orders_created": 0,
        "actual_fills": None,
        "paper_execution": "NOT_ACTIVATED",
        "trading_authority": "NONE",
        "scientific_result": "INSUFFICIENT_EVIDENCE",
    }
    return freeze(out)
