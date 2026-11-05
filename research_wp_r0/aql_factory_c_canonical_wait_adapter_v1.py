"""Factory Package C canonical cross-owner gate adapter.

This module consumes the *actual* Scanner C Frozen SHA receipt and the
read-only, independently validated Core C reconciliation receipt. It never
renames Frozen.sha256 to an invented artifact_sha256, never fabricates an
approval, and never converts a source-only ACK into a strategy-level ACK.

An unproven Scanner synthetic JSON source and a Core original-format ZIP are
NOT SAME SOURCE. In this case the only permissible result is a sealed WAIT,
with NO Lab/Paper invocation. Use the separate Factory B bridge for already
accepted original offline evidence; do not re-run it on Scanner C synthetic.
"""
from __future__ import annotations

from research_wp_r0.aql_factory_unified_backbone_v1 import checked, freeze
from research_wp_r0.aql_factory_same_source_lab_paper_v1 import LabHandoffError

SCHEMA = "aql.factory.c.canonical-strategy-consumer.v1"
WAIT_REASON = "WAIT_SOURCE_PROVENANCE_NOT_CONNECTED"
RECONCILIATION_SCHEMA = "aql.core.c.scanner-source-reconciliation.v1"
APPROVAL_SCHEMA = "aql.scanner-c.strategy-approval.v1"
ROUTE_SCHEMA = "aql.scanner-c.strategy-route-request.v1"
CORE_ROUTE_SCHEMA = "aql.core.c.strategy-secretary-route.v1"


def require(ok, code):
    if not ok:
        raise LabHandoffError("FACTORY_C_CANONICAL_" + code)


def _sealed(item, key):
    try:
        checked(item, key)
    except (TypeError, KeyError, ValueError) as e:
        raise LabHandoffError("FACTORY_C_CANONICAL_BAD_SEAL") from e


def consume_canonical_scanner_core_wait(
    *, scanner_route_receipt, scanner_approval_receipt,
    reconciliation_receipt, core_strategy_route_receipt=None,
    source_only_ack_receipt=None,
):
    """Signed read-only cross-owner reconciliation, no promotion or execution.

    This adapter is intentionally WAIT-only until an independently verified
    same-source receipt, canonically approved strategy-level Core Secretary
    route and explicit Factory consumer ACK exist in one identity domain.
    """
    # Work235 Frozen receipts are {payload,sha256}, not Factory artifact.
    from tools.strategy_service_offline.common import Frozen
    route = Frozen.restore(scanner_route_receipt)
    approval = Frozen.restore(scanner_approval_receipt)
    r, a = route.data, approval.data
    require(r.get("schema") == ROUTE_SCHEMA and a.get("schema") == APPROVAL_SCHEMA,
            "SCANNER_SCHEMA")
    require(r.get("strategy_approval_sha256") == approval.sha256
            and r.get("strategy_id") == a.get("strategy_id")
            and r.get("strategy_version") == a.get("strategy_version")
            and r.get("config_digest") == a.get("config_digest")
            and r.get("definition_digest") == a.get("definition_digest")
            and r.get("dna_digest") == a.get("dna_digest")
            and r.get("timeframe") == "15m"
            and r.get("source_secretary_ack_is_strategy_approval") is False
            and r.get("strategy_secretary_status") == "NOT_ENQUEUED"
            and r.get("work235_operational_15m_status") ==
                "NOT_CONNECTED_15M_UNSUPPORTED"
            and a.get("scope") == "SYNTHETIC_OFFLINE_ENGINEERING_ONLY"
            and a.get("governance_action") in ("APPROVE_TEST_ONLY","DENY_TEST_ONLY")
            and a.get("strategy_governance_status") ==
                a.get("decision")
            and r.get("strategy_governance_status") == a.get("decision")
            and a.get("trading_authority") == "NONE"
            and r.get("trading_authority") == "NONE"
            and a.get("operational_paper_authority") == "NONE"
            and r.get("paper_authority") == "NONE"
            and r.get("historical_known_at_ms") is None,
            "SCANNER_IDENTITY_POLICY_BOUNDARY")
    _sealed(reconciliation_receipt,"reconciliation_sha256")
    c = reconciliation_receipt
    require(c.get("schema") == RECONCILIATION_SCHEMA
            and c.get("decision") == "WAIT"
            and c.get("reason") == "SOURCE_LINEAGE_NOT_CONNECTED"
            and c.get("strategy_secretary_status") == "NOT_ENQUEUED"
            and c.get("scanner_c_route_sha256") == route.sha256
            and c.get("scanner_c_approval_sha256") == approval.sha256
            and c.get("scanner_c_source_raw_sha256") == r.get("source_raw_sha256")
            and c.get("scanner_c_source_manifest_sha256") ==
                r.get("source_manifest_sha256")
            and c.get("scanner_c_universe_sha256") == r.get("universe_sha256")
            and c.get("scanner_c_denominator") == r.get("denominator")
            and c.get("scanner_c_census") == r.get("strategy_census")
            and c.get("strategy_id") == r.get("strategy_id")
            and c.get("strategy_version") == r.get("strategy_version")
            and c.get("config_digest") == r.get("config_digest")
            and c.get("definition_digest") == r.get("definition_digest")
            and c.get("core_source_zip_sha256") == r.get("source_zip_sha256")
            and c.get("core_245_price_query_sha256") ==
                r.get("core245_price_query_sha256")
            and c.get("core_253_query_local_sha256") ==
                r.get("core253_query_local_sha256")
            and c.get("core_cutoff_ms") == r.get("cutoff_ms")
            and c.get("historical_pit") == "NOT_ATTESTED"
            and c.get("operational_scanner_status") == "UNKNOWN"
            and c.get("source_only_ack_is_strategy_approval") is False
            and c.get("paper_execution") == "NOT_ACTIVATED"
            and c.get("trading_authority") == "NONE"
            and c.get("orders_created") == 0
            and c.get("paper_positions") == 0
            and c.get("actual_fills") is None
            and "SCANNER_SYNTHETIC_RAW_TO_CORE_ZIP_NOT_ATTESTED" in
                c.get("blocking_conditions", []),
            "CORE_RECONCILIATION_DRIFT")
    # Refuse a fake strategy ACK in a source-only reconciliation.
    if core_strategy_route_receipt is not None:
        _sealed(core_strategy_route_receipt,"route_receipt_sha256")
        require(core_strategy_route_receipt.get("schema") == CORE_ROUTE_SCHEMA
                and core_strategy_route_receipt.get("route_ready_for_isolated_lab") is False
                and core_strategy_route_receipt.get("paper_authority") == "NONE"
                and core_strategy_route_receipt.get("trading_authority") == "NONE",
                "STRATEGY_ACK_CANNOT_OVERRIDE_UNPROVEN_SOURCE")
    if source_only_ack_receipt is not None:
        _sealed(source_only_ack_receipt,"receipt_sha256")
        require(source_only_ack_receipt.get("receipt_sha256") ==
                c.get("core_source_only_ack_sha256"),
                "SOURCE_ONLY_ACK_PARENT")
    return freeze({
        "schema":SCHEMA,
        "decision":"WAIT",
        "reason":WAIT_REASON,
        "scanner_route_sha256":route.sha256,
        "scanner_approval_sha256":approval.sha256,
        "core_reconciliation_sha256":c["reconciliation_sha256"],
        "core_strategy_route_sha256":None if core_strategy_route_receipt is None
          else core_strategy_route_receipt["route_receipt_sha256"],
        "source_only_ack_sha256":c["core_source_only_ack_sha256"],
        "core_245_price_query_sha256":c["core_245_price_query_sha256"],
        "core_253_query_local_sha256":c["core_253_query_local_sha256"],
        "source_zip_sha256":c["core_source_zip_sha256"],
        "scanner_synthetic_raw_sha256":c["scanner_c_source_raw_sha256"],
        "source_provenance":"NOT_CONNECTED_SAME_SOURCE_NOT_ATTESTED",
        "scanner_strategy_selection":"NOT_PROMOTED_TO_HISTORICAL",
        "source_only_ack_is_strategy_approval":False,
        "strategy_approval_is_trading_authority":False,
        "strategy_secretary_status":"NOT_ENQUEUED",
        "factory_lab_invoked":False,
        "isolated_paper_invoked":False,
        "paper_execution":"NOT_ACTIVATED",
        "trading_authority":"NONE",
        "orders_created":0,
        "paper_positions":0,
        "actual_fills":None,
        "historical_pit":"NOT_ATTESTED",
        "holdout":"SEALED_UNOPENED",
    })
