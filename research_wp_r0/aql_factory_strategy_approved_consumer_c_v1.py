"""ATLAS Factory C: fail-closed TEST_ONLY strategy-approved Secretary consumer.

A source-only Secretary ACK is not a strategy approval. All approval/route
evidence is separately canonical-SHA sealed and must have explicit TEST_ONLY
scope and NONE trading authority. No operational Scanner/Paper promotion.
Versioned provisional handshake until Scanner/Core owners deliver canonical
cross-owner C contracts; incompatible schemas never pass by inference.
"""
from __future__ import annotations

from research_wp_r0.aql_factory_unified_backbone_v1 import checked, freeze
from research_wp_r0.aql_factory_core_query_bridge_v1 import (
    BATCH_SCHEMA, run_isolated_bundle_b,
)
from research_wp_r0.aql_factory_same_source_lab_paper_v1 import LabHandoffError

SCANNER_APPROVAL_SCHEMA = "aql.scanner.strategy-approval-test-only.v1"
CORE_STRATEGY_ROUTE_SCHEMA = "aql.core.secretary-strategy-route.v1"
FACTORY_C_SCHEMA = "aql.factory.strategy-approved-consumer.v1"
PENDING_SCHEMA = "aql.factory.strategy-approved-consumer-wait.v1"
APPROVAL_STATUS = "APPROVED_TEST_ONLY"
DELIVERY_STATUS = "STRATEGY_ACKED"
PIT_SCOPE = "RETROSPECTIVE_NON_PIT"
PAPER_ROUTE = "NOT_CONNECTED_15M_UNSUPPORTED"
SHA_FIELDS = (
    "source_zip_sha256", "manifest_integrity_sha256",
    "core_245_price_query_sha256", "core_253_query_local_sha256",
    "warehouse_receipt_sha256", "decision_cutoff_ms",
)


def _need(value, reason):
    if not value:
        raise LabHandoffError("FACTORY_C_" + reason)


def _sealed(item, key="artifact_sha256"):
    try:
        checked(item, key)
    except (TypeError, ValueError, KeyError) as exc:
        raise LabHandoffError("FACTORY_C_INVALID_SHA_SEAL") from exc
    return item


def _sha(x):
    return type(x) is str and len(x) == 64 and all(c in "0123456789abcdef" for c in x)


def _identity(obj):
    return tuple(obj.get(k) for k in (
        "strategy_id", "strategy_version", "config_digest",
        "strategy_definition_digest", "symbol", "timeframe",
    ))


def _source_parent(obj):
    return tuple(obj.get(k) for k in SHA_FIELDS)


def _status_valid(item):
    return (item.get("operational_scanner_status") == "UNKNOWN"
            and item.get("historical_known_at_ms") is None
            and item.get("historical_pit") == "NOT_ATTESTED"
            and item.get("trading_authority") == "NONE"
            and item.get("paper_execution") == "NOT_ACTIVATED")


def wait_for_unapproved_strategy(reason, *, nomination=None, source_only_ack=None):
    """Conservative WAIT artifact, never an implicit approval."""
    _need(reason in (
        "MISSING_APPROVAL", "EXPIRED_APPROVAL", "SOURCE_ONLY_ACK",
        "MISSING_STRATEGY_ROUTE", "MISSING_STRATEGY_CONSUMER_ACK",
        "RETROSPECTIVE_UNKNOWN", "KNOWN_AT_NOT_ATTESTED",
        "QUARANTINED_STRATEGY_ROUTE"), "INVALID_WAIT_REASON")
    if nomination is not None:
        _sealed(nomination)
    if source_only_ack is not None:
        _sealed(source_only_ack)
    return freeze({
        "schema": PENDING_SCHEMA,
        "decision": "WAIT", "reason": reason,
        "nomination_sha256": None if nomination is None else nomination["artifact_sha256"],
        "source_only_ack_sha256": None if source_only_ack is None else
            source_only_ack["artifact_sha256"],
        "strategy_approved": False,
        "paper_execution": "NOT_ACTIVATED",
        "trading_authority": "NONE",
        "orders_created": 0, "paper_positions": 0,
        "actual_fills": None,
    })


def consume_test_only_strategy_approval(
    source, native_price_query, local_query, calculation,
    nomination, approval, strategy_route, consumer_ack,
    *, source_only_ack=None,
):
    """Read and verify exact signed cross-owner parents then Lab→isolated Paper.

    This does NOT issue an approval, produce a Secretary ACK, select a
    historical nomination, execute a broker order, or attest historical PIT.
    """
    if approval is None:
        return wait_for_unapproved_strategy("MISSING_APPROVAL")
    if strategy_route is None:
        return wait_for_unapproved_strategy("MISSING_STRATEGY_ROUTE")
    if consumer_ack is None:
        return wait_for_unapproved_strategy("MISSING_STRATEGY_CONSUMER_ACK")
    _sealed(nomination)
    _sealed(approval)
    _sealed(strategy_route)
    _sealed(consumer_ack)
    if source_only_ack is not None:
        _sealed(source_only_ack)
    _need(nomination.get("schema") == "aql.scanner.native15m-strategy-nomination.factory-c.v1"
          and approval.get("schema") == SCANNER_APPROVAL_SCHEMA
          and strategy_route.get("schema") == CORE_STRATEGY_ROUTE_SCHEMA
          and consumer_ack.get("schema") == "aql.core.strategy-route-consumer-ack.v1",
          "SCHEMA_OR_SOURCE_ONLY_ROUTE")
    _need(_identity(nomination) == _identity(approval) ==
          _identity(strategy_route) == _identity(consumer_ack)
          and all(type(v) is str and bool(v) for v in _identity(approval))
          and approval["timeframe"] == "15m"
          and nomination["symbol"] == source.get("symbol"),
          "STRATEGY_IDENTITY_DRIFT")
    _need(approval.get("approval_status") == APPROVAL_STATUS
          and approval.get("approval_class") == "ENGINEERING_TEST_ONLY"
          and approval.get("approval_kind") == "EXPLICIT_STRATEGY_POLICY"
          and approval.get("approved_by") not in (None, "", "SOURCE_ACK",
                                                   "SCANNER_SELECTED", "AUTO")
          and approval.get("policy_status") == "TEST_ONLY_UNAPPROVED_FOR_TRADING"
          and approval.get("approval_time_ms") is not None
          and type(approval["approval_time_ms"]) is int
          and approval["approval_time_ms"] >= 0
          and type(approval.get("expires_at_ms")) is int
          and approval["approval_time_ms"] <= source.get("cutoff_ms", -1)
          and approval["approval_time_ms"] <= approval["expires_at_ms"]
          and source["cutoff_ms"] <= approval["expires_at_ms"],
          "APPROVAL_NOT_EXPLICIT_CURRENT_TEST_ONLY")
    _need(approval.get("nomination_sha256") == nomination["artifact_sha256"]
          and strategy_route.get("nomination_sha256") == nomination["artifact_sha256"]
          and strategy_route.get("approval_sha256") == approval["artifact_sha256"]
          and consumer_ack.get("strategy_route_sha256") == strategy_route["artifact_sha256"]
          and strategy_route.get("delivery_status") == DELIVERY_STATUS
          and consumer_ack.get("ack_status") == "ACKED_STRATEGY_CONSUMER"
          and strategy_route.get("source_ack_is_strategy_approval") is False
          and consumer_ack.get("ack_kind") == "STRATEGY_CONSUMER_ONLY"
          and strategy_route.get("source_only_ack_sha256") ==
              (None if source_only_ack is None else source_only_ack["artifact_sha256"]),
          "APPROVAL_VS_SOURCE_ACK_LINEAGE")
    _need(all(_source_parent(x) == _source_parent(nomination)
              for x in (approval, strategy_route, consumer_ack))
          and all(_sha(x.get(k)) for x in (nomination, approval, strategy_route, consumer_ack)
                  for k in SHA_FIELDS if k != "decision_cutoff_ms")
          and all(type(x.get("decision_cutoff_ms")) is int
                  for x in (nomination, approval, strategy_route, consumer_ack))
          and nomination.get("source_zip_sha256") == source.get("source_bytes_sha256")
          and nomination.get("manifest_integrity_sha256") ==
              source.get("manifest_integrity_sha256")
          and nomination.get("warehouse_receipt_sha256") ==
              source.get("core_253_warehouse_receipt_sha256")
          and nomination.get("core_245_price_query_sha256") ==
              native_price_query.get("price_query_sha256")
          and nomination.get("core_253_query_local_sha256") ==
              local_query.get("query_sha256")
          and nomination.get("decision_cutoff_ms") == source.get("cutoff_ms")
          and nomination.get("core_245_price_query_sha256") !=
              nomination.get("core_253_query_local_sha256"),
          "SOURCE_DUAL_SHA_CUTOFF_DRIFT")
    _need(all(_status_valid(x) for x in (
        nomination, approval, strategy_route, consumer_ack)),
        "HISTORICAL_PIT_OR_AUTHORITY_PROMOTION")
    _need(nomination.get("publishable") is False
          and nomination.get("delivery_authorized") is False
          and nomination.get("status") == "UNKNOWN"
          and nomination.get("evidence_class") == PIT_SCOPE
          and strategy_route.get("work235_actual_route") == PAPER_ROUTE
          and consumer_ack.get("orders_created") == 0
          and consumer_ack.get("actual_fills") is None,
          "RETROSPECTIVE_UNKNOWN_OR_PAPER_AUTHORITY")
    _need(approval.get("core_evaluation_sha256") ==
          calculation.get("evaluation_sha256")
          and approval.get("strategy_digest") == calculation.get("strategy_digest")
          and approval.get("strategy_id") == calculation.get("strategy_id")
          and approval.get("strategy_version") == calculation.get("strategy_version")
          and approval.get("strategy_definition_digest") ==
              calculation.get("strategy_digest")
          and approval.get("config_digest") ==
              strategy_route.get("config_digest"),
          "CALCULATION_VS_APPROVED_STRATEGY_DRIFT")
    result = run_isolated_bundle_b(
        source, native_price_query, local_query, calculation)
    _need(result["batch"].get("schema") == BATCH_SCHEMA
          and result["lab"]["strategy_digest"] == approval["strategy_digest"]
          and result["lab"]["strategy_id"] == approval["strategy_id"]
          and result["lab"]["strategy_version"] == approval["strategy_version"]
          and result["paper"]["decision"] in ("WAIT", "REJECT")
          and result["paper"]["orders_created"] == 0
          and result["paper"]["paper_positions"] == 0
          and result["paper"]["actual_fills"] is None,
          "LAB_PAPER_NOT_ISOLATED")
    receipt = freeze({
        "schema": FACTORY_C_SCHEMA,
        "nomination_sha256": nomination["artifact_sha256"],
        "strategy_approval_sha256": approval["artifact_sha256"],
        "strategy_route_sha256": strategy_route["artifact_sha256"],
        "strategy_consumer_ack_sha256": consumer_ack["artifact_sha256"],
        "source_only_ack_sha256": None if source_only_ack is None else
            source_only_ack["artifact_sha256"],
        "factory_query_bridge_sha256": result["bridge"]["artifact_sha256"],
        "core_245_price_query_sha256": result["bridge"]["core_245_price_query_sha256"],
        "core_253_query_local_sha256": result["bridge"]["core_253_query_local_sha256"],
        "core_evaluation_sha256": calculation["evaluation_sha256"],
        "lab_sha256": result["lab"]["artifact_sha256"],
        "isolated_paper_sha256": result["paper"]["artifact_sha256"],
        "strategy_id": approval["strategy_id"],
        "strategy_version": approval["strategy_version"],
        "config_digest": approval["config_digest"],
        "strategy_digest": approval["strategy_digest"],
        "symbol": approval["symbol"],
        "timeframe": "15m",
        "experiment_attempt_id": result["lab"]["attempt_id"],
        "decision": result["paper"]["decision"],
        "engineering_test_only_approval": True,
        "operational_strategy_approval": False,
        "historical_pit": "NOT_ATTESTED",
        "operational_scanner_status": "UNKNOWN",
        "paper_execution": "NOT_ACTIVATED",
        "work235_actual_route": PAPER_ROUTE,
        "orders_created": 0,
        "paper_positions": 0,
        "actual_fills": None,
        "trading_authority": "NONE",
        "holdout": "SEALED_UNOPENED",
    })
    return {"consumer": receipt, "lab": result["lab"], "paper": result["paper"],
            "bridge": result["bridge"]}
