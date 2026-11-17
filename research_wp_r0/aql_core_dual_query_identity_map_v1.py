"""Core #253: independently sealed two-domain price-query identity mapping v1.

Core #245 native price custody and #253 SQLite query_local are distinct
contracts. Replaying their SHA-256 parents independently, this module binds
both to one original source / manifest / dataset / version / cutoff / grid.
No equality between the two QUERY SHAs is required or asserted. Factory
#254 remains owner of its own adapted Lab/source consumer; Work #235 15m
operational Paper routing remains NOT_CONNECTED.
"""
from __future__ import annotations

from research_wp_r0.aql_archive_custody_bridge_v1 import digest
from research_wp_r0.aql_core_backbone_local_v1 import BackboneError, require

SCHEMA = "aql.core.historical-dual-query-identity-map.v1"
NATIVE_SCHEMA = "aql.core.historical-price-custody-query.v1"
LOCAL_SCHEMA = "aql.core.local-history-query.v1"
WAREHOUSE_SCHEMA = "aql.core.local-history-warehouse.v1"
STRATEGY_SCHEMA = "aql.core.offline-lab-test-strategy.v1"


def _sealed(data, key):
    require(type(data) is dict and type(data.get(key)) is str and
            len(data[key]) == 64 and
            digest({k:v for k,v in data.items() if k!=key}) == data[key],
            "CORE_DUAL_QUERY_PARENT_SEAL")


def _identity(value):
    return (
        value.get("dataset_id"),value.get("version"),
        value.get("source_bytes_sha256"),value.get("manifest_integrity_sha256"),
        value.get("decision_cutoff_ms"),
    )


def bind_dual_query_identities(native_price_query, local_query,
                               warehouse_receipt, strategy_evaluation=None):
    """Map two immutable query receipts without rewriting/aliasing their SHA.

    The warehouse receipt must belong to the same sealed original source.
    The original-price domain may have distinct numerical-projection bytes,
    so row SHA equality is not assumed; source/version/manifest/cutoff and
    complete bar-grid identity are required.
    """
    _sealed(native_price_query,"price_query_sha256")
    _sealed(local_query,"query_sha256")
    _sealed(warehouse_receipt,"receipt_sha256")
    require(native_price_query.get("schema")==NATIVE_SCHEMA
            and local_query.get("schema")==LOCAL_SCHEMA
            and warehouse_receipt.get("schema")==WAREHOUSE_SCHEMA,
            "CORE_DUAL_QUERY_SCHEMA")
    require(native_price_query.get("status")=="OK"
            and local_query.get("coverage")=="COMPLETE"
            and native_price_query.get("coverage")=="COMPLETE"
            and local_query.get("missing_bar_opens")==[]
            and native_price_query.get("missing_bar_opens")==[]
            and warehouse_receipt.get("coverage")=="COMPLETE"
            and warehouse_receipt.get("status")=="OFFLINE_LOCAL_WAREHOUSE_COMMITTED"
            and warehouse_receipt.get("vault",{}).get("vault")==
                "EXISTING_PINNED_RAW_VAULT",
            "CORE_DUAL_QUERY_NOT_COMMITTED_OR_COMPLETE")
    require(_identity(native_price_query)==_identity(local_query),
            "CORE_DUAL_QUERY_SOURCE_VERSION_CUTOFF_DRIFT")
    require(native_price_query["source_bytes_sha256"]==
              warehouse_receipt.get("source_zip_sha256")
            and native_price_query["manifest_integrity_sha256"]==
              warehouse_receipt.get("manifest_integrity_sha256")
            and native_price_query["dataset_id"]==warehouse_receipt.get("dataset_id")
            and native_price_query["version"]==warehouse_receipt.get("version")
            and native_price_query["decision_cutoff_ms"]==
                warehouse_receipt.get("decision_cutoff_ms"),
            "CORE_DUAL_QUERY_WAREHOUSE_DRIFT")
    require(local_query.get("source_availability")=="RETROSPECTIVE_NON_PIT"
            and local_query.get("historical_pit")=="NOT_ATTESTED"
            and native_price_query.get("source_availability")=="RETROSPECTIVE_NON_PIT"
            and native_price_query.get("scientific_pit")=="NOT_ATTESTED"
            and native_price_query.get("historical_known_at_ms") is None
            and warehouse_receipt.get("historical_known_at")=="NOT_ATTESTED"
            and warehouse_receipt.get("availability")=="RETROSPECTIVE_NON_PIT"
            and warehouse_receipt.get("execution")=="DISABLED",
            "CORE_DUAL_QUERY_FALSE_PIT_OR_AUTHORITY")
    require(type(native_price_query.get("required_bar_count")) is int
            and type(native_price_query.get("available_bar_count")) is int
            and native_price_query["required_bar_count"]==
                local_query.get("required_bar_count")==
                local_query.get("available_bar_count")==
                native_price_query["available_bar_count"]==
                warehouse_receipt.get("bar_count"),
            "CORE_DUAL_QUERY_BAR_CENSUS")
    original_bars=native_price_query.get("bars")
    indexed_bars=local_query.get("bars")
    require(type(original_bars) is list and type(indexed_bars) is list
            and len(original_bars)==len(indexed_bars)
            and 0<len(original_bars)<=4096,
            "CORE_DUAL_QUERY_BAR_ARRAYS")
    for a,b in zip(original_bars,indexed_bars):
        require(a.get("bar_open_ms")==b.get("bar_open_ms")
                and a.get("bar_close_ms")==b.get("bar_close_ms")
                and a.get("checksum")==b.get("bar_checksum")
                and a.get("observation_lower_bound_ms")==
                    b.get("observation_lower_bound_ms")
                and a.get("historical_known_at_ms") is None
                and b.get("historical_known_at_ms") is None,
                "CORE_DUAL_QUERY_BAR_GRID_OR_CHECKSUM")
    require(all(indexed_bars[i]["bar_open_ms"]<indexed_bars[i+1]["bar_open_ms"]
                for i in range(len(indexed_bars)-1)),
            "CORE_DUAL_QUERY_DUPLICATE_OR_REORDER")
    strategy_sha=None
    if strategy_evaluation is not None:
        _sealed(strategy_evaluation,"evaluation_sha256")
        require(strategy_evaluation.get("schema")==STRATEGY_SCHEMA
                and strategy_evaluation.get("research_lane")==
                    "OFFLINE_LAB_TEST_STRATEGY"
                and strategy_evaluation.get("test_only") is True
                and strategy_evaluation.get("operational_scanner_status")=="UNKNOWN"
                and strategy_evaluation.get("historical_known_at_ms") is None
                and strategy_evaluation.get("real_paper_activation")=="DISABLED"
                and strategy_evaluation.get("trading_authority")=="NONE"
                and strategy_evaluation.get("core_price_query_sha256")==
                    local_query["query_sha256"]
                and strategy_evaluation.get("core_253_query_sha256")==
                    local_query["query_sha256"]
                and strategy_evaluation.get("warehouse_receipt_sha256")==
                    warehouse_receipt["receipt_sha256"]
                and (
                    strategy_evaluation.get("dataset_id"),
                    strategy_evaluation.get("version"),
                    strategy_evaluation.get("source_zip_sha256"),
                    strategy_evaluation.get("manifest_integrity_sha256"),
                    strategy_evaluation.get("decision_cutoff_ms"),
                )==_identity(local_query)
                and strategy_evaluation.get("bar_count")==len(indexed_bars),
                "CORE_DUAL_QUERY_STRATEGY_PARENT_DRIFT")
        strategy_sha=strategy_evaluation["evaluation_sha256"]
    body={
        "schema":SCHEMA,"version":1,
        "dataset_id":native_price_query["dataset_id"],
        "source_version":native_price_query["version"],
        "source_zip_sha256":native_price_query["source_bytes_sha256"],
        "manifest_integrity_sha256":native_price_query["manifest_integrity_sha256"],
        "decision_cutoff_ms":native_price_query["decision_cutoff_ms"],
        "core_245_native_price_query_sha256":
            native_price_query["price_query_sha256"],
        "core_253_query_local_sha256":local_query["query_sha256"],
        "warehouse_receipt_sha256":warehouse_receipt["receipt_sha256"],
        "strategy_evaluation_sha256":strategy_sha,
        "query_shas_are_identical":(
            native_price_query["price_query_sha256"]==local_query["query_sha256"]),
        "distinct_contracts_preserved":True,
        "core_strategy_field_semantics":
            "core_price_query_sha256=CORE_253_QUERY_LOCAL_NOT_CORE_245_NATIVE",
        "query_coverage":"COMPLETE",
        "bar_count":len(indexed_bars),
        "historical_known_at_ms":None,
        "historical_pit":"NOT_ATTESTED",
        "operational_scanner_status":"UNKNOWN",
        "work235_native_15m":"NOT_CONNECTED_15M_UNSUPPORTED",
        "trading_authority":"NONE",
    }
    return {**body,"identity_map_sha256":digest(body)}
