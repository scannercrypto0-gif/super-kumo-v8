"""Factory #254: bounded Core-custody → Lab → offline paper-model seam.

No new warehouse, strategy engine, journal persistence or broker. Reuses the
existing Factory #246 / #250 receipts and main PositionLedger/PaperIntent
contracts. Core #253 RAW/Secretary runtime evidence is separately owned:
an unavailable link is NOT_CONNECTED, never simulated as authenticated.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import asdict
from hashlib import sha256
import json
import re

from research_wp_r0.aql_factory_authentic_research_admission import (
    _digest, _hash, _check_seal,
)
from research_wp_r0.strategy_definition import canonical as research_canonical, digest as research_digest
from src.aql.observation.contracts import PaperIntent
from src.aql.observation.positions import PositionEvent, PositionLedger, PositionContractError

SOURCE_SCHEMA = "aql.factory.unified-custody-source.v1"
LAB_SCHEMA = "aql.factory.unified-lab-ledger.v1"
PAPER_SCHEMA = "aql.factory.offline-paper-model.v1"
E2E_SCHEMA = "aql.factory.unified-offline-e2e.v1"
TRIAL_STATES = frozenset(("PROPOSED", "INVALID", "FAILED", "DUPLICATE",
                          "REJECTED", "UNKNOWN", "BUDGET_EXHAUSTED"))
SCAN_STATES = ("SELECTED", "REJECTED", "UNKNOWN", "UNSCANNED", "INELIGIBLE", "FAILED")


class UnifiedBackboneError(ValueError):
    pass


def need(ok, why):
    if not ok:
        raise UnifiedBackboneError("FACTORY_254_" + why)


def sha(value):
    return _hash(value)


def checked(receipt, field):
    try:
        _check_seal(receipt, field)
    except (ValueError, TypeError, KeyError) as exc:
        raise UnifiedBackboneError("FACTORY_254_SEAL_" + field) from exc
    return receipt


def freeze(obj, key="artifact_sha256"):
    return {**obj, key: _digest(obj)}


def frozen_work_receipt(obj):
    """Read a real Work Frozen.receipt() JSON shape (canonical data SHA)."""
    need(type(obj) is dict and set(obj) == {"payload", "sha256"}
         and type(obj["payload"]) is dict and sha(obj["sha256"]),
         "WORK_RECEIPT_SHAPE")
    try:
        digest = sha256(research_canonical(obj["payload"])).hexdigest()
    except (ValueError, TypeError, OverflowError) as exc:
        raise UnifiedBackboneError("FACTORY_254_WORK_JSON") from exc
    need(digest == obj["sha256"], "WORK_RECEIPT_DIGEST")
    return obj["payload"]


def consume_core_warehouse_query(core_admission, price_query,
                                 chronology_assessment, warehouse_receipt=None):
    """Consume existing Core read-only OHLCV; do not invent #253 RAW receipt.

    A warehouse receipt must come from the future Core-owned #253 contract.
    Until delivered, reject purported link claims and report the actual Core
    custody source/query as bounded/retrospective and RAW link NOT_CONNECTED.
    """
    checked(core_admission, "manifest_record_sha256")
    checked(price_query, "price_query_sha256")
    checked(chronology_assessment, "assessment_sha256")
    need(warehouse_receipt is None, "UNRECOGNIZED_CORE_253_WAREHOUSE_PROOF")
    need(core_admission.get("schema") == "aql.core.historical-original-admission.v1"
         and price_query.get("schema") ==
             "aql.core.historical-price-custody-query.v1"
         and chronology_assessment.get("schema") ==
             "aql.core.chronology-universe-assessment.v1", "CORE_SCHEMA")
    keys = {"dataset_id": "dataset_id", "version": "version",
            "source_bytes_sha256": "source_bytes_sha256",
            "manifest_integrity_sha256": "manifest_integrity_sha256",
            "decision_cutoff_ms": "decision_cutoff_ms"}
    need(all(core_admission.get(a) == price_query.get(b) ==
             chronology_assessment.get(a) for a, b in keys.items()),
         "SOURCE_VERSION_CUTOFF_DRIFT")
    need(chronology_assessment.get("admission_sha256") ==
         core_admission["manifest_record_sha256"]
         and chronology_assessment.get("price_query_sha256") ==
         price_query["price_query_sha256"], "CHRONOLOGY_PARENT")
    need(price_query.get("status") == "OK"
         and price_query.get("scientific_pit") == "NOT_ATTESTED"
         and price_query.get("source_availability") == "RETROSPECTIVE_NON_PIT"
         and chronology_assessment.get("historical_pit") == "NOT_ATTESTED"
         and chronology_assessment.get("market_universe_completeness") == "NOT_ATTESTED"
         and chronology_assessment.get("independent_opportunity_denominator") is None
         and chronology_assessment.get("factory_scientific_input") == "BLOCKED"
         and chronology_assessment.get("trading_authority") == "NONE",
         "FALSE_SOURCE_AUTHORITY")
    coverage = price_query.get("coverage")
    need(coverage in ("COMPLETE", "PARTIAL", "UNKNOWN")
         and coverage == core_admission.get("coverage") ==
         chronology_assessment.get("core_bar_coverage"), "COVERAGE_DRIFT")
    missing = price_query.get("missing_bar_opens")
    required = price_query.get("required_bar_count")
    available = price_query.get("available_bar_count")
    rows = price_query.get("bars")
    need(type(required) is int and type(available) is int
         and type(missing) is list and type(rows) is list
         and 0 <= available <= required <= 100000
         and len(rows) == available
         and available + len(missing) == required
         and core_admission.get("required_bar_count") == required
         and core_admission.get("available_bar_count") == available
         and core_admission.get("missing_bar_opens") == missing,
         "CUSTODY_CENSUS")
    need((coverage == "COMPLETE") == (len(missing) == 0)
         and (coverage == "UNKNOWN") == (available == 0),
         "COVERAGE_STATUS_FALSE")
    seen = set()
    for row in rows:
        need(type(row) is dict and type(row.get("bar_open_ms")) is int
             and row["bar_open_ms"] not in seen
             and sha(row.get("checksum"))
             and row.get("historical_known_at_ms") is None
             and row.get("availability_kind") == "RETROSPECTIVE",
             "CORE_BAR_INTEGRITY")
        seen.add(row["bar_open_ms"])
    need(len(set(missing)) == len(missing)
         and not set(missing).intersection(seen)
         and all(type(t) is int for t in missing), "MISSING_GRID_INTEGRITY")
    output = {
        "schema": SOURCE_SCHEMA,
        "dataset_id": core_admission["dataset_id"],
        "version": core_admission["version"],
        "source_bytes_sha256": core_admission["source_bytes_sha256"],
        "manifest_integrity_sha256":
            core_admission["manifest_integrity_sha256"],
        "native_csv_member_sha256": core_admission.get("native_csv_member_sha256"),
        "original_checksum_file_sha256":
            core_admission.get("native_checksum_file_sha256"),
        "core_admission_sha256": core_admission["manifest_record_sha256"],
        "core_price_query_sha256": price_query["price_query_sha256"],
        "chronology_assessment_sha256":
            chronology_assessment["assessment_sha256"],
        "cutoff_ms": core_admission["decision_cutoff_ms"],
        "coverage": coverage,
        "bar_count_available": available, "bar_count_required": required,
        "missing_bar_opens": missing,
        "original_history_status": "RETROSPECTIVE_NOT_INDEPENDENTLY_PIT",
        "core_query_consumer": (
            "CONNECTED_READ_ONLY_CORE_CUSTODY"
            if coverage == "COMPLETE" else "FAIL_CLOSED_INCOMPLETE_CORE_CUSTODY"),
        "raw_warehouse_query": "NOT_CONNECTED_CORE_253_PENDING",
        "scanner_secretary_real_distribution": "NOT_CONNECTED_CORE_253_PENDING",
        "source_eligible_for_modeling":
            coverage == "COMPLETE",
        "source_eligible_for_historical_pit": False,
        "independent_opportunity_denominator": None,
        "holdout": "SEALED_UNOPENED", "trading_authority": "NONE",
    }
    return freeze(output)


def build_lab_experiment_ledger(source, comparison, trial_ledger,
                                factory_port_reports):
    """Build an immutable experimental *index*, NOT a duplicate evaluator.

    Existing sealed Factory #246 reports are read-only. Every frozen attempt is
    retained; absent reports are NOT_EVALUATED, never silently excluded.
    """
    checked(source, "artifact_sha256")
    checked(comparison, "report_sha256")
    need(source.get("schema") == SOURCE_SCHEMA
         and comparison.get("schema") ==
            "aql.factory.opportunity-comparison-report.v1"
         and comparison.get("scientific_result") == "INSUFFICIENT_EVIDENCE"
         and comparison.get("independent_market_opportunity_denominator") is None
         and comparison.get("base_shadow_comparison") is None
         and comparison.get("trial_attempts") == 53
         and comparison.get("historical_pit") == "NOT_ATTESTED",
         "COMPARISON_SCIENCE_BOUNDARY")
    pins = comparison.get("source_pins")
    need(type(pins) is dict
         and pins.get("archive_sha256") == source["source_bytes_sha256"]
         and pins.get("member_sha256") == source["native_csv_member_sha256"]
         and pins.get("checksum_sha256") ==
         source["original_checksum_file_sha256"]
         and pins.get("core_price_query_sha256") ==
         source["core_price_query_sha256"], "COMPARISON_CORE_IDENTITY")
    need(type(trial_ledger) is list and len(trial_ledger) == 53,
         "FROZEN_TRIAL_DENOMINATOR")
    ids = set()
    candidates = {}
    for t in trial_ledger:
        need(type(t) is dict and set(t) ==
             {"attempt_id", "candidate_digest", "family_id", "state"},
             "TRIAL_SHAPE")
        aid = t["attempt_id"]
        need(type(aid) is str and aid and aid not in ids
             and sha(t["candidate_digest"]) and
             type(t["family_id"]) is str and t["family_id"]
             and t["state"] in TRIAL_STATES, "TRIAL_CENSUS_OR_IDENTITY")
        ids.add(aid)
        candidates[aid] = t
    need(type(factory_port_reports) is list and
         len(factory_port_reports) <= 53, "PORT_REPORT_LIMIT")
    records = {}
    for r in factory_port_reports:
        checked(r, "artifact_sha256")
        need(r.get("schema") == "aql.factory.core-price-rule-port.v1"
             and r.get("core_admission_sha256") ==
             source["core_admission_sha256"]
             and r.get("core_price_query_sha256") ==
             source["core_price_query_sha256"]
             and r.get("source_evidence") in ("TEST_ONLY", "ORIGINAL_UNVERIFIED")
             and r.get("scientific_result") == "INSUFFICIENT_EVIDENCE"
             and r.get("historical_pit") == "NOT_ATTESTED"
             and r.get("trading_authority") == "NONE",
             "FACTORY_PORT_SOURCE_OR_AUTHORITY")
        inner = checked(r.get("factory_report"), "artifact_sha256")
        aid = inner.get("selected_attempt_id")
        need(aid in candidates and aid not in records
             and inner.get("strategy_digest") ==
             candidates[aid]["candidate_digest"]
             and candidates[aid]["state"] == "PROPOSED"
             and inner.get("dataset_id") == source["dataset_id"]
             and inner.get("dataset_version") == source["version"]
             and inner.get("source_bytes_sha256") ==
             source["source_bytes_sha256"]
             and inner.get("source_manifest_sha256") ==
             source["manifest_integrity_sha256"]
             and inner.get("trial_budget") == 53
             and inner.get("scientific_result") == "INSUFFICIENT_EVIDENCE"
             and inner.get("trading_authority") == "NONE",
             "FACTORY_RULE_ATTEMPT_PIN")
        need(type(inner.get("decisions")) is list
             and type(inner.get("decision_slots")) is int
             and inner["decision_slots"] == len(inner["decisions"])
             and type(inner.get("decision_counts")) is dict
             and sum(inner["decision_counts"].values()) ==
             inner["decision_slots"], "FACTORY_DECISION_CENSUS")
        outcomes = inner.get("modeled_outcomes")
        need(type(outcomes) is list and
             all(type(x) is dict and
                 x.get("status") in ("MODEL_ONLY",
                                    "UNKNOWN_INTRABAR_STOP_TARGET",
                                    "UNKNOWN_EXIT_RULE",
                                    "UNKNOWN_END_OF_DATA")
                 and (x.get("modeled_net_return") is None) ==
                 (x.get("status") != "MODEL_ONLY") for x in outcomes),
             "FACTORY_NULL_CENSOR")
        records[aid] = r["artifact_sha256"]
    if source["coverage"] != "COMPLETE":
        need(not records, "PARTIAL_SOURCE_CANNOT_MODEL")
    statuses = Counter(t["state"] for t in trial_ledger)
    ledger = [
        {
            "attempt_id": t["attempt_id"],
            "candidate_digest": t["candidate_digest"],
            "family_id": t["family_id"],
            "trial_state": t["state"],
            "evaluation": ("MODEL_ONLY_RESEARCH_RECEIPT"
                           if t["attempt_id"] in records
                           else "NOT_EVALUATED"),
            "factory_port_sha256": records.get(t["attempt_id"]),
            "scientific_promotion": "NOT_AUTHORIZED",
        } for t in trial_ledger
    ]
    output = {
        "schema": LAB_SCHEMA, "source_sha256": source["artifact_sha256"],
        "comparison_sha256": comparison["report_sha256"],
        "source_class": source["original_history_status"],
        "warehouse_link": source["raw_warehouse_query"],
        "trial_denominator": 53,
        "trial_states": {s: statuses[s] for s in sorted(TRIAL_STATES)},
        "reported_attempts": len(records),
        "not_evaluated_attempts": 53 - len(records),
        "ledger": ledger,
        "universe_denominator": comparison.get("universe_denominator"),
        "independent_opportunity_denominator": None,
        "base_shadow_results": None,
        "modeled_returns_recomputed": False,
        "execution_fills_observed": False,
        "scientific_result": "INSUFFICIENT_EVIDENCE",
        "holdout": "SEALED_UNOPENED", "trading_authority": "NONE",
    }
    return freeze(output)


def build_offline_paper_model_trace(nomination, decision_receipt,
                                   secretary_receipt, position_events=()):
    """Validate Work #235 TEST_ONLY strategy route + existing main position model.

    No order, price fetch, wallet, broker or real paper execution. Secretary
    receipt is an explicitly synthetic bridge; Core #253 real delivery is
    NOT_CONNECTED and cannot be self-certified.
    """
    n = frozen_work_receipt(nomination)
    d = frozen_work_receipt(decision_receipt)
    checked(secretary_receipt, "artifact_sha256")
    need(n.get("schema") == "aql.strategy-nomination.v1"
         and n.get("evidence_class") == "TEST_ONLY"
         and n.get("paper_registry_status") == "NOT_CONNECTED"
         and n.get("trading_authority") == "NONE"
         and n.get("publishable") is False
         and n.get("delivery_authorized") is False,
         "SCANNER_ROUTING_NOT_TEST_ONLY")
    need(n.get("status") in SCAN_STATES
         and type(n.get("cutoff_ms")) is int and n["cutoff_ms"] >= 0
         and type(n.get("reason_codes")) is list
         and sha(n.get("source_raw_sha256"))
         and sha(n.get("feature_snapshot_sha256"))
         and research_digest(n.get("feature_evidence")) == n["feature_snapshot_sha256"],
         "SCANNER_EVIDENCE_OR_CLOCK")
    census = n.get("strategy_census")
    need(type(census) is dict and
         set(census) == {s.lower() for s in SCAN_STATES}
         and all(type(v) is int and v >= 0 for v in census.values())
         and sum(census.values()) == n.get("denominator")
         and census[n["status"].lower()] >= 1,
         "SCANNER_FULL_DENOMINATOR")
    need(n.get("attempt_id") == research_digest({
        "run": n.get("run_id"), "strategy": n.get("config_digest"),
        "symbol": n.get("symbol")}), "SCANNER_ATTEMPT_ID")
    need(secretary_receipt.get("schema") ==
             "aql.factory.secretary-offline-delivery.v1"
         and secretary_receipt.get("mode") == "TEST_ONLY"
         and secretary_receipt.get("delivery_state") ==
             "ACK_TEST_ONLY_ONLY"
         and secretary_receipt.get("nomination_sha256") ==
             nomination["sha256"]
         and secretary_receipt.get("attempt_id") == n["attempt_id"]
         and secretary_receipt.get("strategy_id") == n["strategy_id"]
         and secretary_receipt.get("strategy_version") == n["strategy_version"]
         and secretary_receipt.get("config_digest") == n["config_digest"]
         and secretary_receipt.get("source_raw_sha256") ==
             n["source_raw_sha256"]
         and secretary_receipt.get("cutoff_ms") == n["cutoff_ms"]
         and type(secretary_receipt.get("delivered_ms")) is int
         and secretary_receipt["delivered_ms"] >= n["cutoff_ms"]
         and secretary_receipt.get("real_secretary_ack") is None
         and secretary_receipt.get("trading_authority") == "NONE",
         "SECRETARY_SYNTHETIC_DELIVERY")
    need(d.get("schema") in ("aql.paper-strategy-decision-receipt.v1",
                            "aql.paper-strategy-handoff.v1")
         and d.get("nomination_sha256") == nomination["sha256"]
         and d.get("decision") in ("ACCEPT", "REJECT", "WAIT")
         and d.get("trading_authority") == "NONE"
         and d.get("paper_execution") == "NOT_ACTIVATED",
         "DECISION_SOURCE_OR_AUTHORITY")
    need(d.get("decision") == "WAIT" or n["status"] == "SELECTED",
         "UNSELECTED_STRATEGY_DECISION")
    if d["schema"] == "aql.paper-strategy-decision-receipt.v1":
        need(d.get("strategy_id") == n["strategy_id"]
             and d.get("strategy_version") == n["strategy_version"]
             and d.get("config_digest") == n["config_digest"]
             and d.get("attempt_id") == n["attempt_id"]
             and d.get("consumer_status") == "TEST_ONLY_SINK"
             and d.get("decision_owner") == "STRATEGY_TEST_ONLY_CONSUMER",
             "STRATEGY_DECISION_IDENTITY")
    else:
        need(d.get("consumer_status") ==
             "PAPER_CONSUMER_NOT_CONNECTED"
             and d["decision"] == "WAIT",
             "FALSE_CONNECTED_CONSUMER")
    paper_intent = None
    if d.get("decision") != "WAIT":
        paper_intent = d.get("paper_intent_interface")
        need(type(paper_intent) is dict and
             set(paper_intent) == {"snapshot_id", "intent_id", "status"},
             "PAPER_INTENT_SHAPE")
        want_status = "proposed" if d["decision"] == "ACCEPT" else "declined"
        need(paper_intent == asdict(PaperIntent(nomination["sha256"],
                                               d["delivery_id"], want_status)),
             "PAPER_INTENT_NOT_MAIN_CONTRACT")
    else:
        need(d.get("paper_intent_interface") is None, "WAIT_INTENT_FORBIDDEN")
    need(type(position_events) in (tuple, list)
         and len(position_events) <= 128, "POSITION_EVENT_BUDGET")
    ledger = PositionLedger()
    emitted = []
    pos = set()
    for raw in position_events:
        need(d["decision"] == "ACCEPT"
             and type(raw) is dict
             and set(raw) ==
             {"position_id", "event_id", "kind", "event_ms", "received_ms",
              "source", "price", "reason"}, "SIMULATED_POSITION_ONLY")
        need(raw["source"] == "TEST_ONLY_PAPER_MODEL"
             and raw["event_ms"] >= secretary_receipt["delivered_ms"]
             and raw["received_ms"] >= raw["event_ms"],
             "POSITION_CLOCK_OR_SOURCE")
        try:
            ev = PositionEvent(**raw)
            verdict = ledger.append(ev)
        except (PositionContractError, TypeError, ValueError) as exc:
            raise UnifiedBackboneError("FACTORY_254_POSITION_CONTRACT") from exc
        emitted.append({
            "event_id": ev.event_id, "position_id": ev.position_id,
            "event_sha256": _digest(asdict(ev)),
            "append_disposition": verdict,
        })
        pos.add(ev.position_id)
    output = {
        "schema": PAPER_SCHEMA, "nomination_sha256": nomination["sha256"],
        "strategy_id": n["strategy_id"],
        "strategy_version": n["strategy_version"],
        "config_digest": n["config_digest"],
        "source_raw_sha256": n["source_raw_sha256"],
        "secretary_trace_sha256": secretary_receipt["artifact_sha256"],
        "decision_sha256": decision_receipt["sha256"],
        "decision": d["decision"],
        "paper_intent_nontrading": paper_intent,
        "modeled_positions": [
            {"position_id": x,
             "status": ledger.status(x, max([e["received_ms"] for e in
                                             position_events] + [0])),
             "position_class": "SYNTHETIC_PAPER_MODEL_NOT_A_FILL"}
            for x in sorted(pos)
        ],
        "position_events": emitted,
        "real_secretary_distribution": "NOT_CONNECTED_CORE_253_PENDING",
        "paper_execution": "NOT_ACTIVATED",
        "orders_created": 0,
        "actual_fills": None,
        "scientific_result": "INSUFFICIENT_EVIDENCE",
        "trading_authority": "NONE",
    }
    return freeze(output)


def build_unified_offline_e2e(source, lab, paper=None):
    """Cross-stage summary that refuses to pretend original→Scanner is wired."""
    checked(source, "artifact_sha256")
    checked(lab, "artifact_sha256")
    need(source.get("schema") == SOURCE_SCHEMA
         and lab.get("schema") == LAB_SCHEMA
         and lab.get("source_sha256") == source["artifact_sha256"]
         and lab.get("trial_denominator") == 53
         and lab.get("scientific_result") == "INSUFFICIENT_EVIDENCE",
         "LAB_PARENT")
    paper_link = "PAPER_MODEL_NOT_PROVIDED"
    if paper is not None:
        checked(paper, "artifact_sha256")
        need(paper.get("schema") == PAPER_SCHEMA
             and paper.get("orders_created") == 0
             and paper.get("trading_authority") == "NONE",
             "PAPER_PARENT")
        # Actual source to Scanner bridge requires Core #253 witness and
        # legitimate separate-source transform provenance. Synthetic scans
        # never inherit authenticity from Core original historical ZIPs.
        paper_link = ("TEST_ONLY_SAME_SOURCE_NOT_AUTHENTIC"
                      if paper["source_raw_sha256"] ==
                      source["source_bytes_sha256"]
                      else "NOT_CONNECTED_DIFFERENT_SOURCE_DOMAINS")
    return freeze({
        "schema": E2E_SCHEMA,
        "source_receipt_sha256": source["artifact_sha256"],
        "lab_receipt_sha256": lab["artifact_sha256"],
        "paper_receipt_sha256": None if paper is None
                                 else paper["artifact_sha256"],
        "core_custody_consumer": source["core_query_consumer"],
        "raw_warehouse_link": source["raw_warehouse_query"],
        "factory_lab_link": "CONNECTED_READ_ONLY_RECEIPTS",
        "scanner_secretary_link": paper_link,
        "actual_original_to_raw_warehouse_to_scanner":
            "NOT_CONNECTED_CORE_253_PENDING",
        "genuine_original_offline_paper_model":
            "NOT_CONNECTED_SOURCE_PROVENANCE_REQUIRED",
        "trial_denominator": 53,
        "unknown_opportunity_denominator": None,
        "holdout": "SEALED_UNOPENED",
        "scientific_result": "INSUFFICIENT_EVIDENCE",
        "paper_live_execution": "DISABLED",
        "trading_authority": "NONE",
    })
