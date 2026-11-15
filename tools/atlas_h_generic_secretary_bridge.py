"""Integration Package H: verified generic Factory -> real Core SQLite Secretary.

Keeps the frozen F2-specific atlas_h_research_secretary_bridge unchanged.
No mocks, independent approvals, original data, trading or new database.
"""
from __future__ import annotations

from research_wp_r0.aql_archive_custody_bridge_v1 import digest
from research_wp_r0.aql_core_h_research_secretary_v1 import (
    build_generic_research_result_route,
    route_generic_research_result,
    read_generic_research_result_route,
)


class GenericBridgeError(ValueError):
    pass


def deliver_generic_research_wait(*, secretary_root, packet, factory_package,
                                  factory_result):
    """Validate all cross-owner parent seals before writing durable WAIT."""
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


def _check(ok, code):
    if not ok:
        raise GenericBridgeError("AQL_H_GENERIC_BRIDGE_"+code)
