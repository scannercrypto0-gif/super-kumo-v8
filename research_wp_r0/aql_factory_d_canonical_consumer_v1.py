"""Factory D: canonical, fail-closed Core strategy consumer (synthetic TEST_ONLY).

This module issues an independently Factory-owned ACK for a genuine durable
PENDING_CONSUMER snapshot. It does not mistake that ACK for Lab execution,
does not fabricate a Core source ACK, and does not activate Paper.
"""
from __future__ import annotations

from research_wp_r0.aql_archive_custody_bridge_v1 import digest
from research_wp_r0.aql_factory_same_source_lab_paper_v1 import LabHandoffError

ACK_SCHEMA = "aql.factory.d.canonical-strategy-consumer-ack.v1"
SNAP_SCHEMA = "aql.core.d.canonical-strategy-secretary-snapshot.v1"
GATE_SCHEMA = "aql.core.d.same-source-strategy-route-gate.v1"


def _need(condition, reason):
    if not condition:
        raise LabHandoffError("FACTORY_D_" + reason)


def _sealed(receipt, field):
    _need(type(receipt) is dict and type(receipt.get(field)) is str
          and len(receipt[field]) == 64
          and digest({k: v for k, v in receipt.items() if k != field})
          == receipt[field], "BAD_SEAL")


def accept_pending_strategy_test_only(*, snapshot, gate, source_ack,
                                      route_id, accepted_at_ms,
                                      expires_at_ms):
    """Factory acceptance is distinct from Core durable consumer ACK.

    The caller must subsequently submit the returned ACK through Core D's
    ack_scanner_d_strategy_consumer API and verify an ACKED_CONSUMER snapshot.
    No Lab/Paper execution is asserted here.
    """
    for obj, field in ((snapshot, "route_receipt_sha256"),
                       (gate, "gate_sha256"),
                       (source_ack, "receipt_sha256")):
        _sealed(obj, field)
    _need(snapshot.get("schema") == SNAP_SCHEMA
          and snapshot.get("state") == "PENDING_CONSUMER"
          and snapshot.get("route_ready_for_factory_test_only") is False
          and snapshot.get("consumer_ack_sha256") is None
          and snapshot.get("source_ack_is_strategy_approval") is False
          and snapshot.get("route_id") == route_id
          and gate.get("schema") == GATE_SCHEMA
          and gate.get("decision") == "RESEARCH_CANDIDATE_VERIFIED_TEST_ONLY"
          and gate.get("nomination_status") == "SELECTED"
          and gate.get("scanner_c_governance_action") == "APPROVE_TEST_ONLY"
          and gate.get("scanner_c_scope") == "SYNTHETIC_OFFLINE_ENGINEERING_ONLY"
          and gate.get("historical_pit") == "NOT_ATTESTED"
          and gate.get("historical_known_at_ms") is None
          and snapshot.get("historical_pit") == "NOT_ATTESTED"
          and snapshot.get("historical_known_at_ms") is None
          and snapshot.get("trading_authority") == "NONE"
          and gate.get("trading_authority") == "NONE"
          and snapshot.get("paper_execution") == "NOT_ACTIVATED"
          and snapshot.get("orders_created") == 0
          and snapshot.get("paper_positions") == 0
          and snapshot.get("actual_fills") is None,
          "PENDING_SCOPE_OR_APPROVAL")
    parents = (
        ("gate_sha256", "gate_sha256"),
        ("scanner_c_approval_sha256", "scanner_c_approval_sha256"),
        ("source_ack_sha256", "receipt_sha256"),
        ("strategy_id", "strategy_id"),
        ("strategy_version", "strategy_version"),
        ("config_digest", "config_digest"),
        ("source_zip_sha256", "source_zip_sha256"),
        ("core_245_price_query_sha256", "core_245_price_query_sha256"),
        ("core_253_query_local_sha256", "core_253_query_local_sha256"),
        ("cutoff_ms", "cutoff_ms"),
    )
    _need(all(snapshot.get(a) == gate.get(b)
              for a, b in parents if a != "source_ack_sha256")
          and snapshot.get("source_ack_sha256") == source_ack["receipt_sha256"]
          and gate.get("source_ack_sha256") == source_ack["receipt_sha256"]
          and snapshot.get("scanner_c_nomination_sha256")
              == gate.get("scanner_c_nomination_sha256")
          and snapshot.get("scanner_d_handoff_sha256")
              == gate.get("scanner_d_handoff_sha256")
          and snapshot.get("core_d_witness_sha256")
              == gate.get("core_d_witness_sha256")
          and snapshot.get("strategy_definition_digest")
              == gate.get("strategy_definition_digest")
          and snapshot.get("symbol") == gate.get("symbol") == "AAA"
          and snapshot.get("timeframe") == "15m"
          and snapshot.get("core_245_price_query_sha256")
              != snapshot.get("core_253_query_local_sha256"),
          "PARENT_IDENTITY_DRIFT")
    _need(type(accepted_at_ms) is int and type(expires_at_ms) is int
          and type(gate.get("cutoff_ms")) is int
          and gate["cutoff_ms"] <= accepted_at_ms < expires_at_ms
          and 0 < expires_at_ms - accepted_at_ms <= 600_000,
          "ACK_EXPIRED_OR_CLOCK")
    body = {
        "schema": ACK_SCHEMA, "route_id": route_id,
        "decision": "ACCEPTED_TEST_ONLY_RESEARCH",
        "strategy_gate_sha256": gate["gate_sha256"],
        "scanner_c_approval_sha256": gate["scanner_c_approval_sha256"],
        "source_ack_sha256": source_ack["receipt_sha256"],
        "strategy_id": gate["strategy_id"],
        "strategy_version": gate["strategy_version"],
        "config_digest": gate["config_digest"],
        "source_zip_sha256": gate["source_zip_sha256"],
        "core_245_price_query_sha256": gate["core_245_price_query_sha256"],
        "core_253_query_local_sha256": gate["core_253_query_local_sha256"],
        "cutoff_ms": gate["cutoff_ms"], "accepted_at_ms": accepted_at_ms,
        "trading_authority": "NONE", "paper_authority": "NONE",
        "orders_created": 0, "paper_positions": 0, "actual_fills": None,
    }
    return {**body, "consumer_ack_sha256": digest(body)}
