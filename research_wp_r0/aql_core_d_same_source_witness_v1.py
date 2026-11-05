"""Core D signed software-only same-source cohort witness for Scanner D #262.

Never attests exchange provenance, original-market authenticity, real PIT or
trading. Consumes existing sealed #245/#253 parent receipts and immutable
#226 indexed warehouse; declares only bounded synthetic fixture clocks.
"""
from __future__ import annotations

from research_wp_r0.aql_archive_custody_bridge_v1 import digest as core_digest
from research_wp_r0.aql_core_backbone_local_v1 import query_local
from research_wp_r0.aql_core_dual_query_identity_map_v1 import bind_dual_query_identities
from tools.strategy_service_offline.common import Frozen

SCHEMA = "aql.core.d.synthetic-same-source-research-witness.v1"
WIDTH = 900_000


def _require(value, code):
    if not value:
        raise ValueError("CORE_D_" + code)


def _sealed(obj, field, schema):
    _require(type(obj) is dict and obj.get("schema")==schema
             and isinstance(obj.get(field),str)
             and core_digest({k:v for k,v in obj.items() if k!=field})==obj[field],
             "PARENT_SEAL_"+field)


def create_core_d_research_witness(core_root, warehouse, native_price_query,
                                   local_query, identity_map, *,
                                   scanner_source_id, scanner_generation_id,
                                   scanner_market, research_universe_members,
                                   synthetic_available_at_ms_by_bar):
    """Issue a deterministic software research witness, never a PIT seal.

    Caller explicitly supplies synthetic availability; this API cannot invent
    timestamp availability by equating it with historical market known-at.
    """
    _sealed(warehouse,"receipt_sha256","aql.core.local-history-warehouse.v1")
    _sealed(native_price_query,"price_query_sha256",
            "aql.core.historical-price-custody-query.v1")
    _sealed(local_query,"query_sha256","aql.core.local-history-query.v1")
    _sealed(identity_map,"identity_map_sha256",
            "aql.core.historical-dual-query-identity-map.v1")
    _require(warehouse.get("test_only") is True
             and warehouse.get("status")=="OFFLINE_LOCAL_WAREHOUSE_COMMITTED"
             and warehouse.get("vault",{}).get("vault")=="EXISTING_PINNED_RAW_VAULT"
             and warehouse.get("interval")=="15m"
             and warehouse.get("availability")=="RETROSPECTIVE_NON_PIT"
             and warehouse.get("historical_known_at")=="NOT_ATTESTED"
             and warehouse.get("execution")=="DISABLED"
             and warehouse.get("coverage")=="COMPLETE"
             and 0<warehouse.get("bar_count",0)<=4096,
             "TEST_ONLY_IMMUTABLE_WAREHOUSE")
    verified=bind_dual_query_identities(native_price_query,local_query,warehouse)
    _require(identity_map==verified,"TWO_QUERY_IDENTITY_MAP_DRIFT")
    _require(native_price_query["price_query_sha256"]!=local_query["query_sha256"],
             "QUERY_SHA_DOMAINS_MUST_REMAIN_SEPARATE")
    repeat=query_local(
        core_root,warehouse["dataset_id"],warehouse["version"],
        warehouse["start_ms"],warehouse["end_exclusive_ms"],
        warehouse["decision_cutoff_ms"],
        required_source_sha256=warehouse["source_zip_sha256"],
        require_complete=True)
    _require(repeat==local_query,"CORE_READ_ONLY_REPLAY_MISMATCH")
    for label,value in (("SOURCE_ID",scanner_source_id),
                        ("GENERATION_ID",scanner_generation_id),
                        ("MARKET",scanner_market)):
        _require(type(value) is str and 0<len(value)<=160,label)
    bars=local_query["bars"]
    clocks=synthetic_available_at_ms_by_bar
    _require(type(clocks) is list and len(clocks)==len(bars),"SYNTHETIC_CLOCK_CENSUS")
    for i,(bar,t) in enumerate(zip(bars,clocks)):
        _require(type(t) is dict
                 and set(t)=={"bar_open_ms","bar_checksum","available_at_ms"}
                 and t["bar_open_ms"]==bar["bar_open_ms"]
                 and t["bar_checksum"]==bar["bar_checksum"]
                 and type(t["available_at_ms"]) is int
                 and bar["bar_close_ms"]<t["available_at_ms"]<=warehouse["decision_cutoff_ms"]
                 and bar["bar_open_ms"]==warehouse["start_ms"]+i*WIDTH
                 and bar["bar_close_ms"]==bar["bar_open_ms"]+WIDTH-1
                 and bar["historical_known_at_ms"] is None,
                 "SYNTHETIC_CLOCK_BAR_OR_KNOWN_AT_DRIFT")
    members=research_universe_members
    _require(type(members) is list and 0<len(members)<=256,"UNIVERSE_CENSUS")
    seen=set()
    for m in members:
        _require(type(m) is dict
                 and set(m)=={"symbol","eligible","membership_available_ms"}
                 and type(m["symbol"]) is str and m["symbol"] not in seen
                 and m["eligible"] in (True,False,None)
                 and type(m["membership_available_ms"]) is int
                 and 0<=m["membership_available_ms"]<=warehouse["decision_cutoff_ms"],
                 "UNIVERSE_DUPLICATE_SCOPE_OR_TIME")
        seen.add(m["symbol"])
    _require(warehouse["symbol"] in seen,"SOURCE_SYMBOL_NOT_IN_UNIVERSE")
    # Actual Scanner #262 owner payload is returned WITHOUT extra fields:
    # adding an issuer SHA here would change Scanner's unchanged schema.
    payload={
        "schema":SCHEMA,"scope":"SYNTHETIC_SAME_SOURCE_SOFTWARE_ONLY",
        "source_kind":"CORE_ORIGINAL_FORMAT_TEST_ZIP",
        "source_authority":"TEST_ONLY_NOT_PUBLISHER_ATTESTED",
        "historical_pit":"NOT_ATTESTED",
        "historical_known_at_ms":None,
        "research_clock_basis":"DECLARED_SYNTHETIC_FIXTURE_ONLY",
        "trading_authority":"NONE",
        "dataset_id":warehouse["dataset_id"],
        "version":warehouse["version"],"symbol":warehouse["symbol"],
        "source_zip_sha256":warehouse["source_zip_sha256"],
        "manifest_integrity_sha256":warehouse["manifest_integrity_sha256"],
        "warehouse_receipt_sha256":warehouse["receipt_sha256"],
        "core245_price_query_sha256":native_price_query["price_query_sha256"],
        "core253_query_local_sha256":local_query["query_sha256"],
        "decision_cutoff_ms":warehouse["decision_cutoff_ms"],
        "scanner_source_id":scanner_source_id,
        "scanner_generation_id":scanner_generation_id,
        "scanner_market":scanner_market,
        "synthetic_available_at_ms_by_bar":clocks,
        "research_universe_members":members,
    }
    return Frozen.build(payload).receipt()
