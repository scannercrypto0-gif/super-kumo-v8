"""Package H research-result Secretary adapter; separate from C/D approval routes.

Reuse the existing Core SQLite Secretary connection and SHA event conventions.
A Factory research report is not an independent signature, Source ACK, strategy
approval, Consumer ACK, F5 authorization or paper-trading instruction.
No historical source files are read or written by this adapter.
"""
from __future__ import annotations

import json
import re

from research_wp_r0.aql_archive_custody_bridge_v1 import digest
from research_wp_r0.aql_core_backbone_local_v1 import _connect

SCHEMA = "aql.core.h.research-result-secretary-route.v1"
EVENT_SCHEMA = "aql.core.h.research-result-route-event.v1"
FACTORY_SCHEMA = "aql.factory.f.f2-recovery-research-report.v2"
FACTORY_STATE = "RECOVERY_RESEARCH_ONLY_NOT_F5"
ID = re.compile(r"^[A-Za-z0-9_.:+-]{1,160}$")
HEX = re.compile(r"^[0-9a-f]{64}$")
PARENTS = (
    "input_sha256", "core_receipt_graph_sha256",
    "scanner_receipt_sha256", "lab_sha256",
    "experiment_sha256", "result_sha256",
)


def _need(ok, code):
    if not ok:
        raise ValueError("CORE_H_SECRETARY_" + code)


def _sha(x):
    return type(x) is str and HEX.fullmatch(x) is not None


def _verify_factory(report):
    _need(type(report) is dict and
          report.get("schema") == FACTORY_SCHEMA and
          report.get("status") == FACTORY_STATE and
          _sha(report.get("receipt_sha256")) and
          digest({k: v for k, v in report.items()
                  if k != "receipt_sha256"}) == report["receipt_sha256"],
          "FACTORY_SEALED_RESULT_REQUIRED")
    _need(type(report.get("experiment_id")) is str and
          ID.fullmatch(report["experiment_id"]) is not None and
          all(_sha(report.get(k)) for k in PARENTS),
          "FACTORY_PARENT_IDENTITY")
    _need(type(report.get("attempt_count")) is int and
          report["attempt_count"] == 24 and
          type(report.get("diagnostic_evaluated")) is int and
          report["diagnostic_evaluated"] == 20 and
          type(report.get("feb_aug_inventory_unknown")) is int and
          report["feb_aug_inventory_unknown"] == 4 and
          report.get("historical_pit") == "NOT_ATTESTED" and
          report.get("trading_authority") == "NONE" and
          report.get("holdout") == "SEALED_UNOPENED" and
          report.get("paper") == "NOT_ACTIVATED" and
          report.get("selected") is False and
          type(report.get("orders_created")) is int and
          report["orders_created"] == 0 and
          type(report.get("positions")) is int and
          report["positions"] == 0 and
          report.get("source_ack_sha256") is None and
          report.get("strategy_approval_sha256") is None and
          report.get("factory_consumer_ack_sha256") is None,
          "AUTHORITY_OR_DENOMINATOR_DRIFT")


def build_research_result_route(factory_report, *,
                                strategy_definition_sha256,
                                strategy_config_sha256, code_sha256,
                                cost_policy_sha256, lab_report_sha256):
    """Build an offline-only evidence pointer, never invent any acknowledgments.

    Lab evidence is an independently supplied SHA pointer; this adapter does
    NOT claim Lab metrics or their independent scientific verification.
    """
    _verify_factory(factory_report)
    for sha in (strategy_definition_sha256, strategy_config_sha256,
                code_sha256, cost_policy_sha256, lab_report_sha256):
        _need(_sha(sha), "EXPLICIT_PARENT_REQUIRED")
    _need(lab_report_sha256 != factory_report["lab_sha256"],
          "LAB_EVALUATION_MUST_BE_DISTINCT_FROM_FACTORY_CAUSAL_FOCUS")
    body = {
        "schema": SCHEMA, "experiment_id": factory_report["experiment_id"],
        "state": "WAIT_RESEARCH_REVIEW",
        "factory_report_sha256": factory_report["receipt_sha256"],
        "factory_experiment_sha256": factory_report["experiment_sha256"],
        "factory_result_sha256": factory_report["result_sha256"],
        "factory_causal_focus_sha256": factory_report["lab_sha256"],
        "lab_evaluation_sha256": lab_report_sha256,
        "strategy_definition_sha256": strategy_definition_sha256,
        "strategy_config_sha256": strategy_config_sha256,
        "code_sha256": code_sha256,
        "cost_policy_sha256": cost_policy_sha256,
        "source_graph_sha256": factory_report["core_receipt_graph_sha256"],
        "scanner_receipt_sha256": factory_report["scanner_receipt_sha256"],
        "attempt_count": 24, "evaluated_count": 20,
        "unknown_inventory_count": 4,
        "historical_pit": "NOT_ATTESTED",
        "historical_known_at_ms": None,
        "source_ack_sha256": None,
        "strategy_approval_sha256": None,
        "factory_consumer_ack_sha256": None,
        "research_review_ack_sha256": None,
        "f5_approval": "NOT_GRANTED",
        "paper": "NOT_ACTIVATED", "trading_authority": "NONE",
    }
    return {**body, "receipt_sha256": digest(body)}


def _create(con):
    con.executescript("""
      CREATE TABLE IF NOT EXISTS h_research_result_routes (
        experiment_id TEXT PRIMARY KEY,
        route_sha TEXT NOT NULL,
        route_json TEXT NOT NULL,
        state TEXT NOT NULL
      );
      CREATE TABLE IF NOT EXISTS h_research_result_events (
        seq INTEGER PRIMARY KEY AUTOINCREMENT,
        experiment_id TEXT NOT NULL,
        event_json TEXT NOT NULL,
        event_sha TEXT NOT NULL
      );
      CREATE INDEX IF NOT EXISTS idx_h_research_result_events
        ON h_research_result_events(experiment_id,seq);
    """)


def _verified(con, experiment_id):
    row = con.execute(
        "SELECT route_sha,route_json,state FROM h_research_result_routes "
        "WHERE experiment_id=?", (experiment_id,)).fetchone()
    _need(row is not None, "ROUTE_NOT_FOUND")
    route = json.loads(row[1])
    _need(route.get("schema") == SCHEMA and
          route.get("experiment_id") == experiment_id and
          route.get("state") == "WAIT_RESEARCH_REVIEW" and
          row[2] == route["state"] and
          row[0] == route.get("receipt_sha256") and
          digest({k: v for k, v in route.items()
                  if k != "receipt_sha256"}) == row[0],
          "ROUTE_TAMPER")
    events = con.execute(
        "SELECT event_json,event_sha FROM h_research_result_events "
        "WHERE experiment_id=? ORDER BY seq", (experiment_id,)).fetchall()
    _need(len(events) == 1, "TRACE_COUNT_DRIFT")
    event = json.loads(events[0][0])
    _need(event.get("schema") == EVENT_SCHEMA and
          event.get("experiment_id") == experiment_id and
          event.get("route_sha256") == row[0] and
          event.get("previous_event_sha256") is None and
          event.get("state") == row[2] and
          digest(event) == events[0][1],
          "TRACE_TAMPER")
    return route


def route_research_result(root, factory_report, **parents):
    """Idempotent append-only delivery to existing Secretary SQLite root.

    No ACK issuer exists here: WAIT is deliberate until an independently
    verified research review protocol is supplied by Integration/Audit.
    """
    route = build_research_result_route(factory_report, **parents)
    con = _connect(root)
    try:
        _create(con)
        con.execute("BEGIN IMMEDIATE")
        previous = con.execute(
            "SELECT route_sha FROM h_research_result_routes "
            "WHERE experiment_id=?", (route["experiment_id"],)).fetchone()
        _need(previous is None or previous[0] == route["receipt_sha256"],
              "IDEMPOTENCY_CONFLICT")
        if previous is None:
            con.execute(
                "INSERT INTO h_research_result_routes "
                "(experiment_id,route_sha,route_json,state) VALUES(?,?,?,?)",
                (route["experiment_id"],route["receipt_sha256"],
                 json.dumps(route, sort_keys=True, separators=(",", ":")),
                 route["state"]))
            event = {"schema": EVENT_SCHEMA,
                     "experiment_id": route["experiment_id"],
                     "route_sha256": route["receipt_sha256"],
                     "previous_event_sha256": None,
                     "state": route["state"]}
            con.execute(
                "INSERT INTO h_research_result_events "
                "(experiment_id,event_json,event_sha) VALUES(?,?,?)",
                (route["experiment_id"],json.dumps(
                    event,sort_keys=True,separators=(",",":")),digest(event)))
        result = _verified(con, route["experiment_id"])
        con.commit()
        return result
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()


def read_research_result_route(root, experiment_id):
    _need(type(experiment_id) is str and
          ID.fullmatch(experiment_id) is not None, "EXPERIMENT_ID_REQUIRED")
    con = _connect(root)
    try:
        _create(con)
        return _verified(con, experiment_id)
    finally:
        con.close()

# Additive Generic H lane. Frozen F2 24/20+4 route above is intentionally intact.
GENERIC_ROUTE_SCHEMA = "aql.core.h.generic-research-result-route.v1"
GENERIC_EVENT_SCHEMA = "aql.core.h.generic-research-event.v1"
GENERIC_INPUT = "aql.factory.h.generic-signal-input.v1"
GENERIC_REPORT = "aql.factory.h.generic-execution-report.v1"
GENERIC_LEDGER = "aql.factory.h.generic-trade-event-ledger.v1"
GENERIC_LAB = "aql.factory.h.scientific-lab-report.v1"
GENERIC_REVIEW = "aql.factory.h.generic-secretary-review-receipt.v1"
GENERIC_PACKAGE = "aql.factory.h.generic-immutable-package.v1"
GENERIC_RESULT = "aql.factory.h.generic-research-result.v1"
GENERIC_ECONOMIC = (
    "DIAGNOSTIC_ZERO_COST_NOT_ECONOMICALLY_VALIDATED",
    "EXPLICIT_DECLARED_COST_SCENARIO_NOT_INDEPENDENTLY_ATTESTED",
)
GENERIC_COUNTS = ("expected_bars", "observed_bars", "missing_bars",
                  "decision_slots", "focus_bar_count", "signal_unknown",
                  "entry_signals", "exit_signals", "no_signal_bars",
                  "modeled_trades", "unknown_trades")


def _generic_seal(doc, field="sha256", schema=None):
    _need(type(doc) is dict and _sha(doc.get(field)) and
          (schema is None or doc.get("schema") == schema) and
          digest({k: v for k, v in doc.items() if k != field}) == doc[field],
          "GENERIC_SEAL_OR_SCHEMA_DRIFT")


def build_generic_research_result_route(packet, factory_package, factory_result):
    """Verify Factory generic sealed lineage without recasting it as legacy F2.

    Hashes prove immutable ancestry, NOT trusted external sign-off. Call only
    after Factory/Scanner have verified the real signed-off synthetic contract.
    No private historical source is opened, no ACK is issued.
    """
    _generic_seal(packet, schema=GENERIC_INPUT)
    _generic_seal(factory_package, schema=GENERIC_PACKAGE)
    _generic_seal(factory_result, "receipt_sha256", GENERIC_RESULT)
    report = factory_package.get("factory_report")
    ledger = factory_package.get("trade_event_ledger")
    lab = factory_package.get("scientific_lab")
    proposal = factory_package.get("secretary_research_receipt")
    _generic_seal(report, schema=GENERIC_REPORT)
    _generic_seal(ledger, schema=GENERIC_LEDGER)
    _generic_seal(lab, schema=GENERIC_LAB)
    _generic_seal(proposal, schema=GENERIC_REVIEW)
    _need(type(packet.get("experiment_id")) is str and
          packet["experiment_id"].startswith("RESEARCH-H-GENERIC-") and
          ID.fullmatch(packet["experiment_id"]) is not None and
          all(doc.get("experiment_id") == packet["experiment_id"] for doc
              in (factory_package, factory_result)),
          "GENERIC_EXPERIMENT_ID")
    sha_fields = ("source_query_sha256", "source_bytes_sha256",
                  "manifest_integrity_sha256", "strategy_definition_sha256",
                  "strategy_plugin_sha256", "config_sha256",
                  "scanner_policy_sha256", "scanner_evaluator_code_sha256",
                  "factory_code_sha256")
    _need(all(_sha(packet.get(k)) for k in sha_fields) and
          _sha(report.get("cost_policy_sha256")) and
          _sha(report.get("scanner_batch_sha256")) and
          all(_sha(report.get(k)) for k in ("input_sha256",
              "experiment_sha256", "result_sha256", "ledger_sha256",
              "lab_sha256")) and
          _sha(proposal.get("uncertainty_sha256")),
          "GENERIC_PARENT_SHA_REQUIRED")
    # Every nested Factory/Scanner/source/code/policy identity stays distinct;
    # never equate Core #245 native SHA with #253 bounded query digest.
    _need(
        factory_package["input_sha256"] == report["input_sha256"]
        == factory_result["input_sha256"] == packet["sha256"]
        == ledger["input_sha256"] == lab["experiment_input_sha256"]
        == proposal["experiment_input_sha256"]
        and factory_result["package_sha256"] == factory_package["sha256"]
        and factory_result["factory_report_sha256"] == report["sha256"]
        and factory_result["trade_ledger_sha256"] == ledger["sha256"]
        and factory_result["scientific_lab_sha256"] == lab["sha256"]
        and factory_result["secretary_receipt_sha256"] == proposal["sha256"]
        and factory_result["experiment_sha256"] == report["experiment_sha256"]
        == proposal["experiment_sha256"]
        and factory_result["result_sha256"] == report["result_sha256"]
        == proposal["result_sha256"]
        and report["ledger_sha256"] == lab["ledger_sha256"]
        == proposal["ledger_sha256"] == ledger["sha256"]
        and report["lab_sha256"] == proposal["lab_sha256"] == lab["sha256"]
        and proposal["uncertainty_sha256"] == digest(lab["uncertainty"])
        and packet["source_query_sha256"] == report["source_query_sha256"]
        == proposal["source_query_sha256"] == ledger["source_query_sha256"]
        and packet["source_bytes_sha256"] == report["source_bytes_sha256"]
        == proposal["source_bytes_sha256"] == ledger["source_bytes_sha256"]
        and packet["manifest_integrity_sha256"] ==
            proposal["manifest_integrity_sha256"]
        and packet["strategy_definition_sha256"] ==
            report["strategy_definition_sha256"] ==
            proposal["strategy_definition_sha256"] ==
            ledger["strategy_digest"] == lab["strategy_digest"]
        and packet["strategy_plugin_sha256"] ==
            proposal["strategy_plugin_sha256"] == ledger["scanner_plugin_sha256"]
        and packet["config_sha256"] == report["config_sha256"]
        == proposal["config_sha256"] == ledger["config_sha256"]
        == lab["config_sha256"]
        and packet["scanner_evaluator_code_sha256"] ==
            proposal["scanner_evaluator_code_sha256"]
        and packet["factory_code_sha256"] == report["factory_code_sha256"]
        == proposal["factory_code_sha256"] == ledger["code_sha256"]
        == lab["code_sha256"]
        and packet["scanner_policy_sha256"] ==
            proposal["scanner_signal_policy_sha256"] ==
            ledger["scanner_policy_sha256"]
        and report["scanner_batch_sha256"] ==
            factory_result["scanner_batch_sha256"] ==
            ledger["scanner_receipt_sha256"] == lab["scanner_receipt_sha256"]
        and report["cost_policy_sha256"] ==
            factory_result["cost_policy_sha256"] ==
            proposal["cost_policy_sha256"] == ledger["policy_sha256"]
            == lab["policy_sha256"]
        and packet["decision_cutoff_ms"] == report["decision_cutoff_ms"]
            == proposal["decision_cutoff_ms"],
        "GENERIC_CROSS_PARENT_DRIFT")
    _need(type(packet["decision_cutoff_ms"]) is int and
          packet["decision_cutoff_ms"] >= 0 and
          factory_result.get("store_status") in
              ("STORED_IMMUTABLE", "REPLAY_IDENTICAL") and
          factory_package.get("economic_class") in GENERIC_ECONOMIC and
          report.get("economic_class") ==
              factory_result.get("economic_class") ==
              ledger.get("economic_policy_class") ==
              lab.get("economic_class") ==
              factory_package.get("economic_class") and
          lab.get("assessment") ==
              "DESCRIPTIVE_RESEARCH_ONLY_NO_ALPHA_CLAIM" and
          lab.get("uncertainty", {}).get("economic_claim") ==
              "NOT_ATTESTED",
          "GENERIC_ECONOMIC_OR_CUTOFF_DRIFT")
    cohort = ledger.get("cohort")
    counts = ledger.get("decision_counts")
    events = ledger.get("events")
    outcomes = ledger.get("outcomes")
    _need(type(cohort) is dict and
          cohort.get("cohort_class") == "GENERIC_SCANNER_H" and
          cohort.get("coverage") in ("COMPLETE", "PARTIAL", "UNKNOWN") and
          all(type(cohort.get(k)) is int and cohort[k] >= 0
              for k in GENERIC_COUNTS) and
          type(counts) is dict and
          all(type(v) is int and v >= 0 for v in counts.values()) and
          type(events) is list and type(outcomes) is list and
          cohort["expected_bars"] > 0 and
          cohort["expected_bars"] == cohort["decision_slots"]
          == len(events) and
          cohort["observed_bars"] + cohort["missing_bars"] ==
              cohort["expected_bars"] and
          cohort["observed_bars"] == cohort["focus_bar_count"] and
          sum(counts.values()) == cohort["expected_bars"] and
          sum(counts.get(k, 0) for k in (
              "UNKNOWN", "ENTRY_SIGNAL", "EXIT_SIGNAL", "NO_SIGNAL")) ==
              cohort["expected_bars"] and
          set(counts).issubset({
              "UNKNOWN", "ENTRY_SIGNAL", "EXIT_SIGNAL", "NO_SIGNAL"}) and
          counts.get("UNKNOWN", 0) == cohort["signal_unknown"] and
          counts.get("ENTRY_SIGNAL", 0) == cohort["entry_signals"] and
          counts.get("EXIT_SIGNAL", 0) == cohort["exit_signals"] and
          counts.get("NO_SIGNAL", 0) == cohort["no_signal_bars"] and
          cohort["modeled_trades"] ==
              sum(x.get("status") == "MODEL_ONLY" for x in outcomes) and
          cohort["unknown_trades"] ==
              sum(x.get("status") != "MODEL_ONLY" for x in outcomes) and
          lab.get("cohort") == cohort and
          lab.get("metrics", {}).get("modeled_trade_count") ==
              cohort["modeled_trades"] and
          lab.get("metrics", {}).get("unknown_outcomes") ==
              cohort["unknown_trades"],
          "GENERIC_DENOMINATOR_DRIFT")
    _need((cohort["coverage"] == "COMPLETE" and
           cohort["missing_bars"] == 0) or
          (cohort["coverage"] != "COMPLETE" and
           cohort["signal_unknown"] == cohort["expected_bars"] and
           cohort["modeled_trades"] == 0),
          "GENERIC_GAPPED_SOURCE_QUARANTINE")
    _need(all(type(x) is dict and
              type(x.get("bar_open_ms")) is int and
              type(x.get("decision_cutoff_ms")) is int and
              x["decision_cutoff_ms"] <= packet["decision_cutoff_ms"] and
              _sha(x.get("scanner_event_sha256")) and
              x.get("signal_state") in counts and
              x.get("execution_state") is not None and
              type(x.get("source_observed")) is bool
              for x in events) and
          len({x["bar_open_ms"] for x in events}) == len(events) and
          all(events[i]["bar_open_ms"] < events[i+1]["bar_open_ms"]
              for i in range(len(events)-1)) and
          all(x["bar_open_ms"] < packet["decision_cutoff_ms"]
              for x in events),
          "GENERIC_EVENT_CUTOFF_OR_IDENTITY")
    _need(all(doc.get("trading_authority") == "NONE" for doc in (
              packet, report, ledger, lab, proposal,
              factory_package, factory_result)) and
          all(doc.get("historical_pit") == "NOT_ATTESTED" for doc in (
              packet, report, ledger, proposal, factory_package)) and
          all(doc.get("holdout") == "SEALED_UNOPENED" for doc in (
              packet, report, ledger, proposal, factory_package,
              factory_result)) and
          all(doc.get(k) is None for doc in (packet, report, proposal)
              for k in ("source_ack_sha256",
                        "strategy_approval_sha256",
                        "factory_consumer_ack_sha256")) and
          proposal.get("state") ==
              "RESEARCH_RESULT_READY_FOR_REVIEW_NOT_ACK" and
          proposal.get("paper") == report.get("paper") ==
              factory_result.get("paper") == "NOT_ACTIVATED" and
          report.get("f5") == factory_result.get("f5") ==
              factory_package.get("f5") == "BLOCKED_EXTERNAL_INPUT" and
          lab.get("paper") == "NOT_ACTIVATED" and
          lab.get("research_ready_for_review") is True and
          lab.get("uncertainty", {}).get("holdout_opened") is False,
          "GENERIC_FORGED_AUTHORITY")
    body = {
        "schema": GENERIC_ROUTE_SCHEMA,
        "experiment_id": packet["experiment_id"],
        "state": "WAIT_RESEARCH_REVIEW",
        "input_sha256": packet["sha256"],
        "factory_package_sha256": factory_package["sha256"],
        "factory_report_sha256": report["sha256"],
        "factory_result_sha256": report["result_sha256"],
        "factory_experiment_sha256": report["experiment_sha256"],
        "factory_ledger_sha256": ledger["sha256"],
        "scientific_lab_sha256": lab["sha256"],
        "factory_review_pointer_sha256": proposal["sha256"],
        "scanner_batch_sha256": report["scanner_batch_sha256"],
        "source_query_sha256": report["source_query_sha256"],
        "source_bytes_sha256": report["source_bytes_sha256"],
        "manifest_integrity_sha256": packet["manifest_integrity_sha256"],
        "strategy_definition_sha256": packet["strategy_definition_sha256"],
        "strategy_plugin_sha256": packet["strategy_plugin_sha256"],
        "strategy_config_sha256": packet["config_sha256"],
        "scanner_code_sha256": packet["scanner_evaluator_code_sha256"],
        "factory_code_sha256": packet["factory_code_sha256"],
        "cost_policy_sha256": report["cost_policy_sha256"],
        "decision_cutoff_ms": packet["decision_cutoff_ms"],
        "coverage": cohort["coverage"],
        "expected_bar_count": cohort["expected_bars"],
        "observed_bar_count": cohort["observed_bars"],
        "missing_bar_count": cohort["missing_bars"],
        "unknown_signal_count": cohort["signal_unknown"],
        "no_signal_count": cohort["no_signal_bars"],
        "modeled_trades": cohort["modeled_trades"],
        "unknown_trades": cohort["unknown_trades"],
        "economic_class": report["economic_class"],
        "historical_pit": "NOT_ATTESTED",
        "historical_known_at_ms": None,
        "holdout": "SEALED_UNOPENED",
        "source_ack_sha256": None,
        "strategy_approval_sha256": None,
        "factory_consumer_ack_sha256": None,
        "research_review_ack_sha256": None,
        "f5_approval": "NOT_GRANTED",
        "paper": "NOT_ACTIVATED",
        "trading_authority": "NONE",
    }
    return {**body, "receipt_sha256": digest(body)}


def _generic_create(con):
    con.executescript("""
      CREATE TABLE IF NOT EXISTS h_generic_research_routes (
        experiment_id TEXT PRIMARY KEY,
        route_sha TEXT NOT NULL, route_json TEXT NOT NULL,
        state TEXT NOT NULL
      );
      CREATE TABLE IF NOT EXISTS h_generic_research_events (
        seq INTEGER PRIMARY KEY AUTOINCREMENT,
        experiment_id TEXT NOT NULL, event_json TEXT NOT NULL,
        event_sha TEXT NOT NULL
      );
      CREATE INDEX IF NOT EXISTS idx_h_generic_research_events
        ON h_generic_research_events(experiment_id,seq);
    """)


def _generic_verified(con, experiment_id):
    row = con.execute(
        "SELECT route_sha,route_json,state FROM h_generic_research_routes "
        "WHERE experiment_id=?", (experiment_id,)).fetchone()
    _need(row is not None, "GENERIC_ROUTE_NOT_FOUND")
    doc = json.loads(row[1])
    _need(doc.get("schema") == GENERIC_ROUTE_SCHEMA and
          doc.get("experiment_id") == experiment_id and
          doc.get("state") == row[2] == "WAIT_RESEARCH_REVIEW" and
          doc.get("receipt_sha256") == row[0] and
          digest({k: v for k,v in doc.items()
                  if k != "receipt_sha256"}) == row[0] and
          all(doc.get(k) is None for k in (
              "source_ack_sha256", "strategy_approval_sha256",
              "factory_consumer_ack_sha256", "research_review_ack_sha256")) and
          doc.get("trading_authority") == "NONE" and
          doc.get("paper") == "NOT_ACTIVATED" and
          doc.get("historical_pit") == "NOT_ATTESTED",
          "GENERIC_STORED_ROUTE_TAMPER")
    rows = con.execute(
        "SELECT event_json,event_sha FROM h_generic_research_events "
        "WHERE experiment_id=? ORDER BY seq", (experiment_id,)).fetchall()
    _need(len(rows) == 1, "GENERIC_EVENT_COUNT")
    event = json.loads(rows[0][0])
    _need(event.get("schema") == GENERIC_EVENT_SCHEMA and
          event.get("experiment_id") == experiment_id and
          event.get("route_sha256") == row[0] and
          event.get("previous_event_sha256") is None and
          event.get("state") == "WAIT_RESEARCH_REVIEW" and
          digest(event) == rows[0][1],
          "GENERIC_EVENT_TAMPER")
    return doc


def route_generic_research_result(root, packet, factory_package, factory_result):
    """Idempotent research-only handoff; SAME Secretary SQLite as legacy F2."""
    route = build_generic_research_result_route(
        packet, factory_package, factory_result)
    con = _connect(root)
    try:
        _generic_create(con)
        con.execute("BEGIN IMMEDIATE")
        prior = con.execute(
            "SELECT route_sha FROM h_generic_research_routes "
            "WHERE experiment_id=?", (route["experiment_id"],)).fetchone()
        _need(prior is None or prior[0] == route["receipt_sha256"],
              "GENERIC_IDEMPOTENCY_CONFLICT")
        if prior is None:
            con.execute(
                "INSERT INTO h_generic_research_routes "
                "(experiment_id,route_sha,route_json,state) VALUES(?,?,?,?)",
                (route["experiment_id"], route["receipt_sha256"],
                 json.dumps(route, sort_keys=True,separators=(",",":")),
                 route["state"]))
            event = {
                "schema": GENERIC_EVENT_SCHEMA,
                "experiment_id": route["experiment_id"],
                "route_sha256": route["receipt_sha256"],
                "state": route["state"], "previous_event_sha256": None,
            }
            con.execute(
                "INSERT INTO h_generic_research_events "
                "(experiment_id,event_json,event_sha) VALUES(?,?,?)",
                (route["experiment_id"], json.dumps(event,sort_keys=True,
                     separators=(",",":")), digest(event)))
        doc = _generic_verified(con, route["experiment_id"])
        con.commit()
        return doc
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()


def read_generic_research_result_route(root, experiment_id):
    _need(type(experiment_id) is str and
          ID.fullmatch(experiment_id) is not None,
          "GENERIC_EXPERIMENT_ID_REQUIRED")
    con = _connect(root)
    try:
        _generic_create(con)
        return _generic_verified(con, experiment_id)
    finally:
        con.close()
