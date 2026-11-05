"""Core C read-only reconciliation with the ACTUAL Scanner C #259 owner schemas.

One canonical Scanner C Frozen approval/request is verified using its own
pinned validators. A synthetic native15m scanner JSON source is NOT assumed
to be the same as an immutable Core original-format ZIP, even when an
external caller repeats its ZIP SHA as a declared parent. Thus such a
candidate stays WAIT until independent same-source evidence exists.
No strategy approval, Secretary ACK, LAB or Paper actuation occurs here.
"""
from __future__ import annotations

import json

from research_wp_r0.aql_archive_custody_bridge_v1 import digest
from research_wp_r0.aql_core_backbone_local_v1 import _connect
from research_wp_r0.aql_core_c_strategy_secretary_route_v1 import (
    _sha,_check,_verify_source_ack,
)

SCHEMA = "aql.core.c.scanner-source-reconciliation.v1"


def reconcile_scanner_c_candidate(
    root, *, scanner_route_receipt, scanner_approval_receipt,
    scanner_run_receipt, scanner_nomination_receipt,
    work235_spec_receipt, native15m_policy_receipt,
    identity_map, warehouse_receipt, source_ack_receipt,
):
    """Return SHA-sealed WAIT with *all* parent domains preserved.

    The sole supported scanner contract is the actual Scanner C canonical
    `aql.scanner-c.*.v1` Frozen shape, NOT guessed Factory provisional
    `artifact_sha256` aliases. This will fail closed when frozen/pinned
    Scanner C/Work235 modules are missing in the integration runner.
    """
    from tools.strategy_service_offline.common import Frozen
    from tools.scanner_strategy_c.approval_route import (
        seal_strategy_route_request, verify_test_only_approval,
    )
    scan_route=Frozen.restore(scanner_route_receipt)
    approval=verify_test_only_approval(
        scanner_approval_receipt,work235_spec_receipt,native15m_policy_receipt)
    policy=Frozen.restore(native15m_policy_receipt)
    scan_run=Frozen.restore(scanner_run_receipt)
    nomination=Frozen.restore(scanner_nomination_receipt)
    r=scan_route.data
    verified=seal_strategy_route_request(
        work235_spec_receipt,native15m_policy_receipt,
        scanner_approval_receipt,scanner_run_receipt,scanner_nomination_receipt,
        source_custody_receipt_sha256=r["source_custody_receipt_sha256"],
        core245_price_query_sha256=r["core245_price_query_sha256"],
        core253_query_local_sha256=r["core253_query_local_sha256"],
        source_zip_sha256=r["source_zip_sha256"],
        historical_known_at_ms=r["historical_known_at_ms"],
        source_custody_status=r["source_custody_status"],
        strategy_secretary_status=r["strategy_secretary_status"],
    )
    _check(verified.sha256==scan_route.sha256
           and verified.data==r,"SCANNER_C_PROPOSAL_REPLAY_DRIFT")
    _check(r["strategy_approval_sha256"]==approval.sha256
           and r["scanner_run_sha256"]==scan_run.sha256
           and r["scanner_nomination_sha256"]==nomination.sha256
           and r["native15m_policy_sha256"]==policy.sha256
           and r["source_secretary_ack_is_strategy_approval"] is False
           and r["paper_authority"]=="NONE"
           and r["trading_authority"]=="NONE"
           and r["operational_work235_native15m"]==
               "NOT_CONNECTED_15M_UNSUPPORTED" if
               "operational_work235_native15m" in r else
               r["work235_operational_15m_status"]==
                   "NOT_CONNECTED_15M_UNSUPPORTED",
           "SCANNER_C_IDENTITY_AUTHORITY")
    _sha(identity_map,"identity_map_sha256")
    _sha(warehouse_receipt,"receipt_sha256")
    _sha(source_ack_receipt,"receipt_sha256")
    _check(identity_map.get("schema")==
               "aql.core.historical-dual-query-identity-map.v1"
           and warehouse_receipt.get("schema")==
               "aql.core.local-history-warehouse.v1"
           and warehouse_receipt.get("status")==
               "OFFLINE_LOCAL_WAREHOUSE_COMMITTED"
           and warehouse_receipt.get("vault",{}).get("vault")==
               "EXISTING_PINNED_RAW_VAULT"
           and warehouse_receipt.get("availability")=="RETROSPECTIVE_NON_PIT"
           and warehouse_receipt.get("historical_known_at")=="NOT_ATTESTED"
           and identity_map.get("source_zip_sha256")==
               warehouse_receipt.get("source_zip_sha256")
           and identity_map.get("manifest_integrity_sha256")==
               warehouse_receipt.get("manifest_integrity_sha256")
           and identity_map.get("warehouse_receipt_sha256")==
               warehouse_receipt.get("receipt_sha256")
           and identity_map.get("decision_cutoff_ms")==
               warehouse_receipt.get("decision_cutoff_ms")
           and identity_map.get("historical_known_at_ms") is None
           and identity_map.get("trading_authority")=="NONE",
           "CORE_B_PARENTS_NOT_VERIFIED")
    # Inspect the ACTUAL source-only Core B durable outbox (not the Scanner
    # synthetic nomination). It remains a different scanner digest domain.
    con=_connect(root)
    try:
        mid=source_ack_receipt.get("message_id")
        row=con.execute(
            "SELECT delivery_json FROM distribution_outbox WHERE message_id=?",
            (mid,)).fetchone()
        _check(row is not None,"SOURCE_ONLY_ACK_NOT_DURABLE")
        delivery=json.loads(row[0])
        source_request_parent={
            "source_ack_sha256":source_ack_receipt["receipt_sha256"],
            "strategy_id":delivery["strategy_id"],
            "strategy_version":delivery["strategy_version"],
            "source_zip_sha256":warehouse_receipt["source_zip_sha256"],
            "manifest_integrity_sha256":
                warehouse_receipt["manifest_integrity_sha256"],
            "warehouse_receipt_sha256":warehouse_receipt["receipt_sha256"],
            "scanner_nomination_sha256":
                delivery["scanner_nomination"]["digest"],
        }
        _verify_source_ack(con,source_request_parent,source_ack_receipt)
    finally:
        con.close()
    reasons=[]
    def block(condition,reason):
        if condition:
            reasons.append(reason)
    block(r["strategy_id"]!=delivery["strategy_id"]
          or r["strategy_version"]!=delivery["strategy_version"],
          "STRATEGY_ID_VERSION_DIFFERENT_FROM_SOURCE_OUTBOX")
    block(r["source_zip_sha256"]!=warehouse_receipt["source_zip_sha256"],
          "SCANNER_DECLARED_CORE_ZIP_PARENT_DRIFT")
    block(r["source_custody_receipt_sha256"]!=warehouse_receipt["receipt_sha256"],
          "SCANNER_DECLARED_CORE_CUSTODY_PARENT_DRIFT")
    block(r["core245_price_query_sha256"]!=
          identity_map["core_245_native_price_query_sha256"]
          or r["core253_query_local_sha256"]!=
          identity_map["core_253_query_local_sha256"],
          "SCANNER_DECLARED_DUAL_QUERY_PARENT_DRIFT")
    block(r["symbol"]!=warehouse_receipt["symbol"],
          "SCANNER_SYMBOL_NOT_CORE_ORIGINAL")
    block(r["cutoff_ms"]!=warehouse_receipt["decision_cutoff_ms"],
          "SCANNER_CUTOFF_NOT_CORE_ORIGINAL")
    block(r["source_custody_status"]=="RETROSPECTIVE_NON_PIT" and
          r["scanner_nomination_status"] in ("SELECTED","REJECTED"),
          "HISTORICAL_NON_PIT_SCANNER_SELECTION_DENIED")
    block(approval.data["decision"]!="APPROVED_TEST_ONLY" or
          r["strategy_governance_status"]!="APPROVED_TEST_ONLY" or
          r["strategy_route_status"]!="ROUTE_CANDIDATE_TEST_ONLY",
          "NO_EXPLICIT_TEST_ONLY_ROUTE_CANDIDATE")
    # A binary original ZIP and independent synthetic JSON have separate
    # SHA domains. Even when the *declared* ZIP parent equals Core's source
    # hash there is NO signed original→synthetic provenance bridge here.
    block(True,"SCANNER_SYNTHETIC_RAW_TO_CORE_ZIP_NOT_ATTESTED")
    body={
        "schema":SCHEMA,"decision":"WAIT","reason":"SOURCE_LINEAGE_NOT_CONNECTED",
        "blocking_conditions":sorted(set(reasons)),
        "scanner_c_route_sha256":scan_route.sha256,
        "scanner_c_approval_sha256":approval.sha256,
        "scanner_c_policy_sha256":policy.sha256,
        "scanner_c_run_sha256":scan_run.sha256,
        "scanner_c_nomination_sha256":nomination.sha256,
        "scanner_c_source_raw_sha256":r["source_raw_sha256"],
        "scanner_c_source_manifest_sha256":r["source_manifest_sha256"],
        "scanner_c_universe_sha256":r["universe_sha256"],
        "scanner_c_denominator":r["denominator"],
        "scanner_c_census":r["strategy_census"],
        "scanner_c_nomination_status":r["scanner_nomination_status"],
        "scanner_c_strategy_governance_status":approval.data["decision"],
        "strategy_id":r["strategy_id"],
        "strategy_version":r["strategy_version"],
        "config_digest":r["config_digest"],
        "definition_digest":r["definition_digest"],
        "scanner_c_cutoff_ms":r["cutoff_ms"],
        "core_cutoff_ms":warehouse_receipt["decision_cutoff_ms"],
        "core_source_zip_sha256":warehouse_receipt["source_zip_sha256"],
        "core_manifest_integrity_sha256":
            warehouse_receipt["manifest_integrity_sha256"],
        "core_245_price_query_sha256":
            identity_map["core_245_native_price_query_sha256"],
        "core_253_query_local_sha256":
            identity_map["core_253_query_local_sha256"],
        "core_warehouse_receipt_sha256":warehouse_receipt["receipt_sha256"],
        "core_source_only_ack_sha256":source_ack_receipt["receipt_sha256"],
        "core_legacy_source_nomination_sha256":
            delivery["scanner_nomination"]["digest"],
        "source_only_ack_is_strategy_approval":False,
        "historical_known_at_ms":None,"historical_pit":"NOT_ATTESTED",
        "operational_scanner_status":"UNKNOWN",
        "strategy_secretary_status":"NOT_ENQUEUED",
        "factory_consumer_ack":None,"paper_execution":"NOT_ACTIVATED",
        "trading_authority":"NONE","orders_created":0,
        "paper_positions":0,"actual_fills":None,
        "discoverer_dependency":"OPTIONAL",
    }
    return {**body,"reconciliation_sha256":digest(body)}
