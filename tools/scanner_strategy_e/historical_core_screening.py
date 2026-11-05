"""ATLAS Scanner E: fail-closed historical Core-query strategy screening.

No synthetic source generation, no invented bar availability/PIT, no operation
of an approved-Paper policy, and no Discoverer dependency. Reads Core #245
and #253 receipts and the actual immutable indexed SQLite/Core stage only.

IMPORTANT: frozen Scanner B/C native15m selects only validated TEST_ONLY
sources. For retrospective original-market evidence the exact historical bars
are retained in an evidence-only census; the corresponding canonical TEST_ONLY
route can never be marked SELECTED or enqueued to Core Secretary.
"""
from __future__ import annotations

from research_wp_r0.aql_archive_custody_bridge_v1 import digest as core_digest
from research_wp_r0.aql_core_backbone_local_v1 import query_local
from research_wp_r0.aql_core_dual_query_identity_map_v1 import bind_dual_query_identities
from tools.strategy_service_offline.common import Frozen, require
from tools.scanner_strategy_b.native15m import native_15m_policy
from tools.scanner_strategy_c.approval_route import explicit_test_only_approval
from tools.strategy_service_offline.screening import StrategyScreeningSpec

SCHEMA = "aql.scanner-e.historical-core-screening.v1"
ATTEMPT_SCHEMA = "aql.scanner-e.historical-strategy-attempt.v1"
STEP = 900_000


def _sealed(obj, key, schema):
    require(type(obj) is dict and obj.get("schema") == schema
            and type(obj.get(key)) is str and len(obj[key]) == 64
            and core_digest({k:v for k,v in obj.items() if k != key})
                == obj[key], "E_CORE_SEAL_OR_SCHEMA_"+key)


def _historical_wait(reason, *, query_sha256=None, source_sha256=None):
    return Frozen.build({
        "schema": SCHEMA, "decision": "WAIT",
        "reason": reason, "source_zip_sha256": source_sha256,
        "core_253_query_local_sha256": query_sha256,
        "original_historical_screening": "NOT_VERIFIED",
        "strategy_secretary_state": "NOT_ENQUEUED",
        "factory_consumer_ack": None,
        "historical_known_at_ms": None, "historical_pit": "NOT_ATTESTED",
        "work235_operational_15m": "NOT_CONNECTED_15M_UNSUPPORTED",
        "paper_execution": "NOT_ACTIVATED",
        "orders_created": 0, "paper_positions": 0,
        "actual_fills": None, "trading_authority": "NONE",
    }).receipt()


def screen_historical_core_query(
    core_root, *, warehouse, native_price_query, local_query, identity_map,
    work_specs, governance_actions, symbol_budget=1,
):
    """One-source retrospective census; intentionally no canonical route candidate.

    Actual Core original admission/issuer proof stays Core-owned. This function
    takes already admitted receipts; no ZIP/CSV/vault construction or writes.
    'UNKNOWN' is mandatory for each retrospective strategy attempt since Core
    only provides observation LOWER BOUND, not historical available_at/PIT.
    """
    if any(x is None for x in (
            warehouse, native_price_query, local_query, identity_map)):
        return _historical_wait("WAIT_SOURCE_PROVENANCE_NOT_CONNECTED")
    _sealed(warehouse, "receipt_sha256", "aql.core.local-history-warehouse.v1")
    _sealed(native_price_query, "price_query_sha256",
            "aql.core.historical-price-custody-query.v1")
    _sealed(local_query, "query_sha256", "aql.core.local-history-query.v1")
    _sealed(identity_map, "identity_map_sha256",
            "aql.core.historical-dual-query-identity-map.v1")
    require(type(work_specs) is list and 0 < len(work_specs) <= 16
            and type(governance_actions) is dict
            and type(symbol_budget) is int and 1 <= symbol_budget <= 256,
            "E_STRATEGY_AND_GOVERNANCE_ARGUMENTS")
    require(warehouse.get("interval") == "15m"
            and warehouse.get("status") in (
                "OFFLINE_LOCAL_WAREHOUSE_COMMITTED",
                "OFFLINE_LOCAL_STAGE_ONLY")
            and warehouse.get("availability") == "RETROSPECTIVE_NON_PIT"
            and warehouse.get("historical_known_at") == "NOT_ATTESTED"
            and warehouse.get("execution") == "DISABLED"
            and warehouse.get("coverage") == "COMPLETE"
            and local_query.get("coverage") == "COMPLETE"
            and local_query.get("historical_pit") == "NOT_ATTESTED"
            and native_price_query.get("status") == "OK"
            and local_query.get("source_availability") == "RETROSPECTIVE_NON_PIT"
            and identity_map.get("historical_pit") == "NOT_ATTESTED"
            and warehouse.get("test_only") is False,
            "E_ORIGINAL_RETROSPECTIVE_ONLY")
    expected_map = bind_dual_query_identities(
        native_price_query,local_query,warehouse)
    require(expected_map == identity_map
            and native_price_query["price_query_sha256"]
                != local_query["query_sha256"]
            and warehouse["source_zip_sha256"]
                == local_query["source_bytes_sha256"]
                == native_price_query["source_bytes_sha256"]
            and warehouse["receipt_sha256"]
                == identity_map["warehouse_receipt_sha256"]
            and local_query["manifest_integrity_sha256"]
                == warehouse["manifest_integrity_sha256"]
            and local_query["decision_cutoff_ms"]
                == warehouse["decision_cutoff_ms"],
            "E_DUAL_QUERY_AND_SOURCE_PARENT_DRIFT")
    replay = query_local(
        core_root, warehouse["dataset_id"], warehouse["version"],
        warehouse["start_ms"], warehouse["end_exclusive_ms"],
        warehouse["decision_cutoff_ms"],
        required_source_sha256=warehouse["source_zip_sha256"],
        require_complete=True)
    require(replay == local_query, "E_SQLITE_IMMUTABLE_REPLAY_DRIFT")
    bars=local_query["bars"]
    require(0 < len(bars) <= 4096
            and len(bars)==warehouse["bar_count"]
            and warehouse["start_ms"]%STEP == 0
            and warehouse["end_exclusive_ms"]
                == warehouse["start_ms"]+len(bars)*STEP
            and all(
                type(b["bar_open_ms"]) is int
                and b["bar_open_ms"]==warehouse["start_ms"]+i*STEP
                and b["bar_close_ms"]==b["bar_open_ms"]+STEP-1
                and b["historical_known_at_ms"] is None
                and type(b["observation_lower_bound_ms"]) is int
                and b["observation_lower_bound_ms"]>=b["bar_close_ms"]
                for i,b in enumerate(bars)),
            "E_BAR_GRID_PIT_OR_FUTURE_DATA")
    cutoff=warehouse["decision_cutoff_ms"]
    require(all(b["bar_close_ms"] < cutoff for b in bars)
            and warehouse["end_exclusive_ms"] <= cutoff,
            "E_FUTURE_BAR_DENIED")
    symbols={warehouse["symbol"]}
    policies=[native_15m_policy(x).receipt() for x in work_specs]
    keys={(x["payload"]["strategy_id"],x["payload"]["strategy_version"])
          for x in policies}
    require(len(keys)==len(policies)
            and set(governance_actions)==keys,
            "E_FROZEN_STRATEGY_IDENTITY_OR_ACTION_SET")
    decisions={}
    for w,p in zip(work_specs,policies):
        spec=StrategyScreeningSpec.restore_spec(w)
        pd=p["payload"]
        require(pd["work235_config_digest"]==spec.data["config_digest"]
                and pd["timeframe"]=="15m"
                and pd["operational_work235_15m"]
                    =="NOT_CONNECTED_15M_UNSUPPORTED",
                "E_FROZEN_POLICY_CONFIG_DRIFT")
        key=(pd["strategy_id"],pd["strategy_version"])
        action=governance_actions[key]
        require(type(action) is dict and set(action)=={
            "action","approver_id","governance_policy_id","approval_nonce"},
            "E_EXPLICIT_ACTION_ARGUMENTS")
        decisions[key]=explicit_test_only_approval(w,p,**action).receipt()
    # No synthetic available_at is introduced. The retrospective per-attempt
    # statuses cannot be SELECTED/REJECTED based on a historical PIT claim.
    entries=[]
    for policy in sorted(policies,key=lambda x:x["payload"]["strategy_id"]):
        pd=policy["payload"]
        key=(pd["strategy_id"],pd["strategy_version"])
        approval=decisions[key]
        allowed=pd["dna"]["dna"]["scanner_profile"]["allowed_symbols"]
        entry_status=("INELIGIBLE" if warehouse["symbol"] not in allowed
                      or pd["market"]!="fixture"
                      else "UNKNOWN")
        reason=("FROZEN_STRATEGY_UNIVERSE_OR_MARKET_INELIGIBLE"
                if entry_status=="INELIGIBLE"
                else "RETROSPECTIVE_KNOWN_AT_NOT_ATTESTED")
        attempt={
            "schema":ATTEMPT_SCHEMA,
            "strategy_id":pd["strategy_id"],
            "strategy_version":pd["strategy_version"],
            "config_digest":pd["config_digest"],
            "work235_config_digest":pd["work235_config_digest"],
            "definition_digest":pd["definition"]["digest"],
            "dna_digest":pd["dna"]["digest"],
            "native15m_policy_sha256":policy["sha256"],
            "work235_spec_sha256":pd["work235_policy_receipt_sha256"],
            "symbol":warehouse["symbol"],"timeframe":"15m",
            "source_zip_sha256":warehouse["source_zip_sha256"],
            "warehouse_receipt_sha256":warehouse["receipt_sha256"],
            "core_245_price_query_sha256":
                native_price_query["price_query_sha256"],
            "core_253_query_local_sha256":local_query["query_sha256"],
            "core_dual_query_map_sha256":identity_map["identity_map_sha256"],
            "scanner_c_test_only_approval_sha256":approval["sha256"],
            "governance_action":approval["payload"]["governance_action"],
            "source_evidence_class":"RETROSPECTIVE_NON_PIT",
            "attempt_status":entry_status,"reason":reason,
            "route_status":"WAIT",
            "strategy_secretary_state":"NOT_ENQUEUED",
            "historical_known_at_ms":None,"historical_pit":"NOT_ATTESTED",
            "trading_authority":"NONE",
        }
        entries.append(Frozen.build(attempt).receipt())
    counts={name:sum(x["payload"]["attempt_status"]==name for x in entries)
            for name in ("SELECTED","REJECTED","UNKNOWN","INELIGIBLE",
                         "DENIED","UNSCANNED","FAILED")}
    require(len(entries)==len(work_specs)*len(symbols)
            and sum(counts.values())==len(entries)
            and counts["SELECTED"]==0
            and all(x["payload"]["route_status"]=="WAIT"
                    for x in entries),
            "E_HISTORICAL_CENSUS_OR_AUTHORITY_DRIFT")
    return Frozen.build({
        "schema":SCHEMA,"decision":"WAIT",
        "reason":"WAIT_HISTORICAL_PIT_NOT_ATTESTED",
        "source_zip_sha256":warehouse["source_zip_sha256"],
        "warehouse_receipt_sha256":warehouse["receipt_sha256"],
        "manifest_integrity_sha256":warehouse["manifest_integrity_sha256"],
        "core_245_price_query_sha256":
            native_price_query["price_query_sha256"],
        "core_253_query_local_sha256":local_query["query_sha256"],
        "core_dual_query_map_sha256":identity_map["identity_map_sha256"],
        "cutoff_ms":cutoff,"symbol":warehouse["symbol"],
        "timeframe":"15m",
        "source_bar_count":len(bars),
        "historical_bar_checksum_list":[b["bar_checksum"] for b in bars],
        "strategy_count":len(work_specs),"symbol_denominator":len(symbols),
        "total_attempts":len(entries),"attempt_census":counts,
        "attempts":entries,
        "strategy_approvals":[decisions[key] for key in sorted(decisions)],
        "canonical_historical_strategy_route":
            "WAIT_NOT_ELIGIBLE_FOR_SYNTHETIC_CANONICAL_ROUTE",
        "strategy_secretary_state":"NOT_ENQUEUED",
        "factory_consumer_ack":None,
        "historical_known_at_ms":None,
        "historical_pit":"NOT_ATTESTED",
        "work235_operational_15m":"NOT_CONNECTED_15M_UNSUPPORTED",
        "discoverer_dependency":"NONE",
        "paper_execution":"NOT_ACTIVATED",
        "orders_created":0,"paper_positions":0,"actual_fills":None,
        "trading_authority":"NONE",
    }).receipt()
