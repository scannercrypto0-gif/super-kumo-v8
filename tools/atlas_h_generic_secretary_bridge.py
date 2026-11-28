"""Integration Package H: verified generic Factory -> real Core SQLite Secretary.

Keeps the frozen F2-specific atlas_h_research_secretary_bridge unchanged.
No mocks, independent approvals, original data, trading or new database.
"""
from __future__ import annotations

from time import time_ns

from research_wp_r0.aql_archive_custody_bridge_v1 import digest
from research_wp_r0.aql_core_h_research_secretary_v1 import (
    build_generic_research_result_route,
    route_generic_research_result,
    read_generic_research_result_route,
)


class GenericBridgeError(ValueError):
    pass


def deliver_generic_research_wait(*, secretary_root, packet, factory_package,
                                  factory_result, lane=None, source_scope=None,
                                  warehouse_root=None):
    """Route legacy WAIT or classify an explicitly typed research result.

    source_scope comes from trusted operator configuration, never the packet.
    """
    _check(lane in (None, "EXPERIMENTAL", "RESEARCH_VALIDATED"),
           "RESEARCH_LANE_FORBIDDEN")
    if lane is not None:
        return _classify_research(lane, packet, factory_package, factory_result,
                                  source_scope, warehouse_root)
    _check(source_scope is None and warehouse_root is None,
           "RESEARCH_LANE_REQUIRED")
    expected=build_generic_research_result_route(
        packet, factory_package, factory_result)
    _check(expected["state"]=="WAIT_RESEARCH_REVIEW"
           and expected["trading_authority"]=="NONE"
           and expected["paper"]=="NOT_ACTIVATED"
           and expected["f5_approval"]=="NOT_GRANTED"
           and expected["historical_pit"]=="NOT_ATTESTED"
           and expected["holdout"]=="SEALED_UNOPENED"
           and all(expected.get(k) is None for k in (
               "source_ack_sha256","strategy_approval_sha256",
               "factory_consumer_ack_sha256","research_review_ack_sha256")),
           "UNAUTHORIZED_ROUTE")
    written=route_generic_research_result(
        secretary_root,packet,factory_package,factory_result)
    reread=read_generic_research_result_route(
        secretary_root,packet["experiment_id"])
    _check(written==expected==reread
           and digest({k:v for k,v in reread.items()
                       if k!="receipt_sha256"})==reread["receipt_sha256"],
           "DURABLE_READBACK_DRIFT")
    return {
        "schema":"aql.integration.h.generic-secretary-delivery.v1",
        "experiment_id":packet["experiment_id"],
        "input_sha256":packet["sha256"],
        "factory_package_sha256":factory_package["sha256"],
        "factory_result_sha256":factory_result["receipt_sha256"],
        "scientific_lab_sha256":factory_package["scientific_lab"]["sha256"],
        "secretary_route_sha256":reread["receipt_sha256"],
        "status":"WAIT_RESEARCH_REVIEW",
        "historical_pit":"NOT_ATTESTED",
        "economic_status":"NOT_INDEPENDENTLY_ATTESTED",
        "f5":"BLOCKED_EXTERNAL_INPUT",
        "trading_authority":"NONE",
    }


def _classify_research(lane, packet, factory_package, factory_result,
                       source_scope, warehouse_root):
    # Imported only by the new research route. Legacy WAIT is unchanged.
    from research_wp_r0.aql_core_backbone_local_v1 import query_local
    from research_wp_r0.aql_factory_h_generic_signal_adapter_v1 import _verified

    _check(type(packet) is dict and type(packet.get("core_query")) is dict,
           "RESEARCH_QUERY_REQUIRED")
    query = packet["core_query"]
    _check(type(source_scope) is dict and set(source_scope) == {
        "dataset_id", "version", "source_bytes_sha256",
        "manifest_integrity_sha256", "query_sha256", "decision_cutoff_ms",
        "rights_reference", "valid_until_ms",
    }, "TRUSTED_SOURCE_SCOPE_REQUIRED")
    _check(all(source_scope[key] == query.get(key) for key in (
        "dataset_id", "version", "source_bytes_sha256",
        "manifest_integrity_sha256", "query_sha256", "decision_cutoff_ms",
    )) and type(source_scope["rights_reference"]) is str
        and bool(source_scope["rights_reference"].strip())
        and type(source_scope["valid_until_ms"]) is int
        and time_ns() // 1_000_000 < source_scope["valid_until_ms"],
        "SOURCE_SCOPE_MISMATCH_OR_EXPIRED")
    _check(warehouse_root is not None, "RESEARCH_WAREHOUSE_REQUIRED")

    batch, _, _, _, cost_policy, batch_sha = _verified(packet)
    _check(batch["source_class"] == "OWNER_LOCAL_RECOVERY_DIAGNOSTIC",
           "DIAGNOSTIC_SOURCE_CLASS_REQUIRED")
    checked = build_generic_research_result_route(
        packet, factory_package, factory_result)
    _check(checked["scanner_batch_sha256"] == batch_sha
           and checked["cost_policy_sha256"] == cost_policy["sha256"],
           "RESEARCH_EVIDENCE_MISMATCH")
    actual = query_local(
        warehouse_root, query["dataset_id"], query["version"],
        query["start_ms"], query["end_exclusive_ms"], query["decision_cutoff_ms"],
        required_source_sha256=query["source_bytes_sha256"],
        require_complete=True, sqlite_immutable=True,
    )
    _check(actual == query, "RESEARCH_SOURCE_READBACK_DRIFT")

    # Generic H only supports retrospective and in-sample evidence. A caller
    # cannot use a lane label to upgrade that producer's evidence contract.
    requested_validation = lane == "RESEARCH_VALIDATED"
    body = {
        "schema": "aql.integration.research-authority.v1",
        "policy_version": "generic-h-evidence-v1",
        "requested_lane": lane,
        "lane": "EXPERIMENTAL",
        "status": "BLOCKED" if requested_validation else "ACCEPTED",
        "reason": ("PIT_OOS_VALIDATION_EVIDENCE_UNAVAILABLE"
                   if requested_validation else None),
        "experiment_id": packet["experiment_id"],
        "input_sha256": packet["sha256"],
        "source_scope_sha256": digest(source_scope),
        "source_query_sha256": query["query_sha256"],
        "factory_package_sha256": factory_package["sha256"],
        "factory_result_sha256": factory_result["receipt_sha256"],
        "scientific_lab_sha256": factory_package["scientific_lab"]["sha256"],
        "source_availability": "RETROSPECTIVE_NON_PIT",
        "historical_pit": "NOT_ATTESTED",
        "paper": "NOT_ACTIVATED",
        "trading_authority": "NONE",
        "secretary_enqueued": False,
    }
    return {**body, "receipt_sha256": digest(body)}


def _check(ok, code):
    if not ok:
        raise GenericBridgeError("AQL_H_GENERIC_BRIDGE_"+code)
