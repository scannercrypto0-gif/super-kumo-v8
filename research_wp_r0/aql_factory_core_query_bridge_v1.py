"""Versioned Factory #254 Bundle B: Core #245 / #253 immutable query bridge.

This is a provenance adapter, not a numerical evaluator, source importer or
Paper order router. Both query domains remain independently signed.
"""
from __future__ import annotations

from research_wp_r0.aql_factory_unified_backbone_v1 import (
    SOURCE_SCHEMA, checked, freeze,
)
from research_wp_r0.aql_factory_same_source_lab_paper_v1 import (
    LabHandoffError, admit_core_lab_calculation,
    isolate_test_only_paper_decision,
)

BRIDGE_SCHEMA = "aql.factory.core-query-identity-bridge.v1"
BATCH_SCHEMA = "aql.factory.bundle-b-isolated-e2e.v1"


def need(condition, code):
    if not condition:
        raise LabHandoffError("FACTORY_B_" + code)


def bridge_core_query_identities(source, native_price_query,
                                 core_local_query, core_calculation):
    """Return sealed (bridge, adapted_source) after independently checking both.

    Caller must first use existing consume_core_warehouse_query() to construct
    source from verified native #245 admission, #245 query and #253 warehouse.
    The adapter never overwrites the native price-query identity in the bridge.
    """
    checked(source, "artifact_sha256")
    checked(native_price_query, "price_query_sha256")
    checked(core_local_query, "query_sha256")
    checked(core_calculation, "evaluation_sha256")
    need(source.get("schema") == SOURCE_SCHEMA
         and source.get("raw_warehouse_query") ==
             "CONNECTED_PINNED_CORE_253_RAW_WAREHOUSE"
         and source.get("core_query_consumer") ==
             "CONNECTED_READ_ONLY_CORE_CUSTODY"
         and source.get("coverage") == "COMPLETE"
         and source.get("missing_bar_opens") == []
         and source.get("source_eligible_for_historical_pit") is False
         and source.get("holdout") == "SEALED_UNOPENED"
         and source.get("trading_authority") == "NONE",
         "SOURCE_AUTHORITY")
    need(native_price_query.get("schema") ==
             "aql.core.historical-price-custody-query.v1"
         and core_local_query.get("schema") ==
             "aql.core.local-history-query.v1",
         "QUERY_SCHEMAS")
    native_sha = native_price_query["price_query_sha256"]
    local_sha = core_local_query["query_sha256"]
    need(source.get("core_price_query_sha256") == native_sha
         and source.get("core_253_warehouse_query_sha256") == local_sha
         and core_calculation.get("core_253_query_sha256") == local_sha
         and core_calculation.get("core_price_query_sha256") == local_sha,
         "QUERY_SHA_DOMAIN_DRIFT")
    need(native_price_query.get("dataset_id") ==
             core_local_query.get("dataset_id") ==
             core_calculation.get("dataset_id") == source.get("dataset_id")
         and native_price_query.get("version") ==
             core_local_query.get("version") ==
             core_calculation.get("version") == source.get("version")
         and native_price_query.get("source_bytes_sha256") ==
             core_local_query.get("source_bytes_sha256") ==
             core_calculation.get("source_zip_sha256") ==
             source.get("source_bytes_sha256")
         and native_price_query.get("manifest_integrity_sha256") ==
             core_local_query.get("manifest_integrity_sha256") ==
             core_calculation.get("manifest_integrity_sha256") ==
             source.get("manifest_integrity_sha256")
         and native_price_query.get("decision_cutoff_ms") ==
             core_local_query.get("decision_cutoff_ms") ==
             core_calculation.get("decision_cutoff_ms") ==
             source.get("cutoff_ms"),
         "SOURCE_IDENTITY_DRIFT")
    need(core_calculation.get("warehouse_receipt_sha256") ==
             source.get("core_253_warehouse_receipt_sha256")
         and core_local_query.get("coverage") == "COMPLETE"
         and core_local_query.get("missing_bar_opens") == []
         and core_local_query.get("available_bar_count") ==
             source.get("bar_count_available")
         and core_local_query.get("required_bar_count") ==
             source.get("bar_count_required")
         and core_calculation.get("bar_count") ==
             source.get("bar_count_available")
         and core_calculation.get("width_ms") == 900_000
         and core_calculation.get("operational_scanner_status") == "UNKNOWN"
         and core_calculation.get("trading_authority") == "NONE"
         and core_calculation.get("historical_known_at_ms") is None,
         "SOURCE_SCOPE_OR_AUTHORITY")
    bridge = freeze({
        "schema": BRIDGE_SCHEMA,
        "source_receipt_sha256": source["artifact_sha256"],
        "core_245_price_query_sha256": native_sha,
        "core_253_query_local_sha256": local_sha,
        "core_evaluation_sha256": core_calculation["evaluation_sha256"],
        "dataset_id": source["dataset_id"],
        "version": source["version"],
        "source_zip_sha256": source["source_bytes_sha256"],
        "manifest_integrity_sha256": source["manifest_integrity_sha256"],
        "warehouse_receipt_sha256":
            source["core_253_warehouse_receipt_sha256"],
        "decision_cutoff_ms": source["cutoff_ms"],
        "native_price_query_and_local_query_same_contract": False,
        "native_query_identity_preserved": True,
        "adapter_field_semantics":
            "core_price_query_sha256=CORE_253_QUERY_LOCAL_FOR_TEST_STRATEGY",
        "scanner_operational_status": "UNKNOWN",
        "historical_known_at_ms": None,
        "scientific_result": "INSUFFICIENT_EVIDENCE",
        "holdout": "SEALED_UNOPENED",
        "trading_authority": "NONE",
    })
    # Existing Factory lab consumer expects Core's query_local in the
    # source.core_price_query_sha256 field. This is a new sealed *projection*,
    # not a mutation or false equivalence of the native #245 price query.
    adapted = freeze({
        **{k: v for k, v in source.items() if k != "artifact_sha256"},
        "core_price_query_sha256": local_sha,
        "core_245_native_price_query_sha256": native_sha,
        "core_query_identity_bridge_sha256": bridge["artifact_sha256"],
    })
    return bridge, adapted


def run_isolated_bundle_b(source, native_price_query, core_local_query,
                          core_calculation):
    """Single offline deterministic batch: versioned bridge → Lab → Paper.

    Does not run Core strategy computation or ingest data. Never executes an
    operational Paper route; Work #235 15m remains NOT_CONNECTED.
    """
    bridge, adapted = bridge_core_query_identities(
        source, native_price_query, core_local_query, core_calculation)
    lab = admit_core_lab_calculation(adapted, core_calculation)
    paper = isolate_test_only_paper_decision(lab)
    need(lab["source_receipt_sha256"] == adapted["artifact_sha256"]
         and lab["core_lab_evaluation_sha256"] ==
             core_calculation["evaluation_sha256"]
         and paper["lab_receipt_sha256"] == lab["artifact_sha256"]
         and paper["source_zip_sha256"] == bridge["source_zip_sha256"]
         and paper["work235_actual_route"] ==
             "NOT_CONNECTED_15M_UNSUPPORTED"
         and paper["decision"] in ("REJECT", "WAIT")
         and paper["orders_created"] == 0
         and paper["paper_positions"] == 0
         and paper["paper_position_events"] == 0
         and paper["actual_fills"] is None
         and paper["trading_authority"] == "NONE",
         "PAPER_ISOLATION")
    receipt = freeze({
        "schema": BATCH_SCHEMA,
        "core_245_price_query_sha256": bridge["core_245_price_query_sha256"],
        "core_253_query_local_sha256": bridge["core_253_query_local_sha256"],
        "bridge_sha256": bridge["artifact_sha256"],
        "adapted_source_sha256": adapted["artifact_sha256"],
        "core_evaluation_sha256": core_calculation["evaluation_sha256"],
        "lab_sha256": lab["artifact_sha256"],
        "paper_sha256": paper["artifact_sha256"],
        "strategy_digest": lab["strategy_digest"],
        "attempt_id": lab["attempt_id"],
        "decision_slots": lab["decision_slots"],
        "paper_decision": paper["decision"],
        "work235_route": "NOT_CONNECTED_15M_UNSUPPORTED",
        "trading_authority": "NONE",
        "orders_created": 0,
        "holdout": "SEALED_UNOPENED",
    })
    return {"bridge": bridge, "adapted_source": adapted,
            "lab": lab, "paper": paper, "batch": receipt}
