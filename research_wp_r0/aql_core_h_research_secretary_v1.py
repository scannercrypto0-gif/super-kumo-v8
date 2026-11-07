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
