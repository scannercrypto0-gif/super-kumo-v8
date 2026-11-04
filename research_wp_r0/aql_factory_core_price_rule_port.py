"""Factory #246: strict read-only native Core #245 OHLCV → rule projection port.

Core original ZIP/CSV/receipt/checksum authenticity and chronology remain Core/
Work/Audit responsibilities. This port independently verifies the *returned*
Core custody/admission and price-query commitments and never upgrades them to
PIT or scientific execution eligibility.
"""
from __future__ import annotations

from research_wp_r0.aql_factory_authentic_research_admission import (
    ResearchAdmissionError, _check_seal, _digest, _hash, _require, seal,
)
from research_wp_r0.aql_factory_historical_rule_projection import (
    evaluate_historical_rules,
)

PLAN_SCHEMA = "aql.factory.historical-rule-work-plan.v1"
PORT_REPORT = "aql.factory.core-price-rule-port.v1"
CORE_ADMISSION = "aql.core.historical-original-admission.v1"
CORE_PRICE = "aql.core.historical-price-custody-query.v1"
CORE_SOURCE_RESULT = "aql.bridge.custody-range.v1"


def from_core_original_price_query(admission, price_query, research_plan):
    """Pin exact native Core source/query/price records to a Factory report.

    Input objects are copies of *actual* upstream schema-shaped results; this
    function cannot authenticate an external vendor, 2024 source publication
    clock, independent checksum issuer, or whole-market universe.
    """
    _check_seal(admission, "manifest_record_sha256")
    _check_seal(price_query, "price_query_sha256")
    _check_seal(research_plan, "artifact_sha256")
    _require(admission.get("schema") == CORE_ADMISSION
             and admission.get("status") in (
                 "TEST_ONLY_INTEGRITY_VERIFIED",
                 "ORIGINAL_PIN_MATCHED_PROVENANCE_PENDING"),
             "CORE_ADMISSION_STATUS")
    _require(admission.get("source_kind") == "BINANCE_KLINES_ZIP"
             and _hash(admission.get("native_csv_member_sha256"))
             and _hash(admission.get("native_checksum_file_sha256"))
             and _hash(admission.get("source_bytes_sha256"))
             and _hash(admission.get("manifest_integrity_sha256"))
             and _hash(admission.get("packet_sha256"))
             and _hash(admission.get("custody_receipt_sha256")),
             "NATIVE_ORIGINAL_LINEAGE")
    _require(all(admission.get(k) == "NOT_ATTESTED" for k in (
        "authenticated_source", "independent_provenance",
        "source_available_at_cutoff", "confirmed_pit",
        "complete_market_universe"))
             and admission.get("factory_scientific_input") == "BLOCKED"
             and admission.get("paper_live_trading") == "DISABLED",
             "FALSE_CORE_AUTHORITY")
    _require(admission.get("coverage") == "COMPLETE"
             and admission.get("missing_bar_opens") == [],
             "CORE_INCOMPLETE")
    _require(price_query.get("schema") == CORE_PRICE
             and price_query.get("status") == "OK"
             and price_query.get("error") is None
             and price_query.get("coverage") == "COMPLETE"
             and price_query.get("missing_bar_opens") == []
             and price_query.get("scientific_pit") == "NOT_ATTESTED"
             and price_query.get("source_availability") ==
             "RETROSPECTIVE_NON_PIT"
             and price_query.get("factory_scientific_input") ==
             "BLOCKED_PENDING_INDEPENDENT_EVIDENCE"
             and price_query.get("paper_live_trading") == "DISABLED"
             and price_query.get("numeric_projection") ==
             "HISTORICAL_LIBRARY_FLOAT_FROM_ORIGINAL_NATIVE_DECIMALS"
             and price_query.get("historical_known_at_ms") is None,
             "CORE_PRICE_AUTHORITY")
    _require(research_plan.get("schema") == PLAN_SCHEMA
             and research_plan.get("holdout") == "SEALED_UNOPENED"
             and research_plan.get("execution_authority") == "NONE"
             and research_plan.get("market") == "SPOT"
             and research_plan.get("direction") == "LONG",
             "ORIGINAL_SPOT_RESEARCH_ONLY")
    # This source implementation's market membership is not independently
    # attested in its query envelope; never infer derivative/perp from spot ZIP.
    ids = ("dataset_id", "version", "source_bytes_sha256",
           "manifest_integrity_sha256", "decision_cutoff_ms")
    for field in ids:
        expected = (research_plan.get(field)
                    if field != "version"
                    else research_plan.get("dataset_version"))
        _require(admission.get(field) == price_query.get(field) == expected,
                 "CORE_PRICE_IDENTITY_" + field.upper())
    _require(research_plan.get("correction_parent_source_sha256") ==
             admission.get("correction_parent_source_sha256"),
             "CORE_CORRECTION_PARENT")
    if admission["version"] > 1:
        _require(_hash(admission.get("correction_parent_source_sha256"))
                 and type(admission.get("correction_reason")) is str
                 and bool(admission["correction_reason"].strip()),
                 "CORRECTION_LINEAGE")
    else:
        _require(admission.get("correction_parent_source_sha256") is None
                 and admission.get("correction_reason") is None,
                 "UNEXPECTED_CORRECTION")
    _require(type(admission.get("query")) is dict
             and admission["query"].get("status") == "OK"
             and type(admission["query"].get("result")) is dict
             and admission["query"]["result"].get("schema") == CORE_SOURCE_RESULT,
             "CORE_QUERY_PROOF")
    base = admission["query"]["result"]
    _require(all(base.get(k) == admission.get(k) for k in (
        "dataset_id", "version", "source_bytes_sha256",
        "manifest_integrity_sha256", "decision_cutoff_ms"))
             and base.get("status") == "COMPLETE"
             and base.get("missing_bar_opens") == [],
             "CORE_QUERY_SCOPE")
    rows = price_query.get("bars")
    base_rows = base.get("bars")
    _require(type(rows) is list and len(rows) >= 2
             and type(base_rows) is list and len(base_rows) == len(rows)
             and all(type(x.get(k)) is int and x[k] == len(rows)
                     for x in (price_query, admission, base)
                     for k in ("required_bar_count", "available_bar_count")),
             "CORE_PRICE_DENOMINATOR")
    normal = []
    for raw, witness in zip(rows, base_rows):
        _require(type(raw) is dict and type(witness) is dict
                 and _hash(raw.get("checksum"))
                 and raw.get("checksum") == witness.get("checksum")
                 and raw.get("bar_open_ms") == witness.get("bar_open")
                 and raw.get("bar_close_ms") == witness.get("bar_close")
                 and raw.get("observation_lower_bound_ms") ==
                 witness.get("observation_cutoff_ms")
                 and raw.get("availability_kind") == "RETROSPECTIVE"
                 and witness.get("availability_kind") == "RETROSPECTIVE"
                 and raw.get("historical_known_at_ms") is None,
                 "CORE_PRICE_BAR_SHA_OR_AVAILABILITY")
        _require(type(raw.get("observation_lower_bound_ms")) is int
                 and raw["bar_close_ms"] <
                 raw["observation_lower_bound_ms"] <=
                 price_query["decision_cutoff_ms"],
                 "CORE_PRICE_OBSERVATION_LOWER_BOUND")
        bar = {
            "open_ms": raw["bar_open_ms"],
            "close_ms": raw["bar_close_ms"],
            "open": raw["open"], "high": raw["high"],
            "low": raw["low"], "close": raw["close"],
            "volume": raw["volume"], "known_at_ms": None,
            "quality": "FINAL",
        }
        bar["bar_sha256"] = _digest(bar)
        normal.append(bar)
    _require(price_query["decision_cutoff_ms"] >= normal[-1]["close_ms"] + 1,
             "PRICE_FUTURE_WINDOW")
    _require(type(research_plan.get("trial_budget")) is int
             and research_plan["trial_budget"] == 53
             and _hash(research_plan.get("plan_digest")),
             "FROZEN_PLAN_IDENTITY")
    packet = {
        "schema": "aql.factory.historical-rule-projection.v1",
        "source_kind": ("TEST_ONLY" if admission["status"] ==
                        "TEST_ONLY_INTEGRITY_VERIFIED" else
                        "ORIGINAL_UNVERIFIED"),
        "availability": ("SYNTHETIC_TEST" if admission["status"] ==
                         "TEST_ONLY_INTEGRITY_VERIFIED" else
                         "RETROSPECTIVE_NON_PIT"),
        "dataset_id": admission["dataset_id"],
        "dataset_version": admission["version"],
        "source_bytes_sha256": admission["source_bytes_sha256"],
        "source_manifest_sha256": admission["manifest_integrity_sha256"],
        "width_ms": research_plan["width_ms"],
        "market": research_plan["market"],
        "direction": research_plan["direction"],
        "holdout": research_plan["holdout"],
        "execution_authority": research_plan["execution_authority"],
        "plan_digest": research_plan["plan_digest"],
        "trial_budget": research_plan["trial_budget"],
        "trials": research_plan["trials"],
        "selected_attempt_id": research_plan["selected_attempt_id"],
        "strategy": research_plan["strategy"],
        "universe": research_plan["universe"],
        "opportunity_count": research_plan["opportunity_count"],
        "opportunities": research_plan["opportunities"],
        "research_window": research_plan["research_window"],
        "costs": research_plan["costs"], "bars": normal,
    }
    report = evaluate_historical_rules(seal(packet))
    _require(report["scientific_result"] == "INSUFFICIENT_EVIDENCE"
             and report["source_original_bytes_verified"] is False
             and report["historical_pit_verified"] is False
             and report["trading_authority"] == "NONE",
             "FALSE_SCIENTIFIC_PROMOTION")
    output = {
        "schema": PORT_REPORT, "research_plan_sha256": research_plan["artifact_sha256"],
        "core_admission_sha256": admission["manifest_record_sha256"],
        "core_native_csv_member_sha256": admission["native_csv_member_sha256"],
        "core_original_checksum_file_sha256":
            admission["native_checksum_file_sha256"],
        "core_price_query_sha256": price_query["price_query_sha256"],
        "core_bar_checksum_list_sha256": _digest([r["checksum"] for r in rows]),
        "factory_report": report,
        "source_evidence": packet["source_kind"],
        "authentic_source_attestation": "NOT_ATTESTED",
        "historical_pit": "NOT_ATTESTED",
        "rule_trigger_evaluation": "TEST_ONLY_OR_RETROSPECTIVE_UNVERIFIED",
        "scientific_result": "INSUFFICIENT_EVIDENCE",
        "holdout": "SEALED_UNOPENED",
        "trading_authority": "NONE",
    }
    output["artifact_sha256"] = _digest(output)
    return output
