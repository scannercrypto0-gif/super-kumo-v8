"""Scanner D: read-only exact Core RAW -> warehouse query -> Scanner 15m adapter.

Research-only synthetic same-source witness. This module never ingests, creates,
or rewrites Core source objects, never infers genuine historical known-at and
never converts independent old Scanner JSON into a Core original ZIP.
"""
from __future__ import annotations

from tools.strategy_service_offline.common import Frozen, canonical, digest, raw_sha, require
from tools.scanner_strategy_c.service import scan_and_prepare_test_only_routes

PROOF_SCHEMA = "aql.scanner-d.core-query-projection.v1"
CORE_D_WITNESS_SCHEMA = "aql.core.d.synthetic-same-source-research-witness.v1"
WIDTH_MS = 900_000


def _sealed_core(obj, key, *, schema=None):
    require(type(obj) is dict and type(obj.get(key)) is str
            and len(obj[key]) == 64
            and digest({k:v for k,v in obj.items() if k != key}) == obj[key],
            "D_CORE_SEALED_PARENT_DRIFT:"+key)
    if schema is not None:
        require(obj.get("schema") == schema, "D_CORE_PARENT_SCHEMA:"+key)


def _project(core_root, warehouse, native_price_query, local_query, dual_map,
             core_d_witness_receipt):
    """Re-read ACTUAL Core indexed source, independently validate #245 vs #253.

    Core D witness is a versioned TEST_ONLY research availability record; the
    witness SHA itself is NOT an issuer signature/PIT certification. The
    evidence is valid only for the synthetic software-cohort software gate.
    """
    from research_wp_r0.aql_core_backbone_local_v1 import query_local
    from research_wp_r0.aql_core_dual_query_identity_map_v1 import bind_dual_query_identities

    _sealed_core(warehouse, "receipt_sha256", schema="aql.core.local-history-warehouse.v1")
    _sealed_core(native_price_query, "price_query_sha256",
                 schema="aql.core.historical-price-custody-query.v1")
    _sealed_core(local_query, "query_sha256",
                 schema="aql.core.local-history-query.v1")
    _sealed_core(dual_map, "identity_map_sha256",
                 schema="aql.core.historical-dual-query-identity-map.v1")
    require(warehouse.get("test_only") is True
            and warehouse.get("status") == "OFFLINE_LOCAL_WAREHOUSE_COMMITTED"
            and warehouse.get("interval") == "15m"
            and warehouse.get("historical_known_at") == "NOT_ATTESTED"
            and warehouse.get("availability") == "RETROSPECTIVE_NON_PIT"
            and warehouse.get("execution") == "DISABLED"
            and warehouse.get("coverage") == "COMPLETE",
            "D_SOURCE_ONLY_TEST_AND_RETROSPECTIVE")
    # Validate every original bar checksum and native/indexed source relation
    # using Core's actual independent receipt verifier, NOT a SHA label alias.
    verified = bind_dual_query_identities(
        native_price_query, local_query, warehouse)
    require(all(verified[k] == dual_map[k] for k in (
        "source_zip_sha256", "manifest_integrity_sha256",
        "core_245_native_price_query_sha256", "core_253_query_local_sha256",
        "warehouse_receipt_sha256", "decision_cutoff_ms",
        "dataset_id", "source_version", "bar_count"))
        and dual_map["core_245_native_price_query_sha256"]
            != dual_map["core_253_query_local_sha256"],
        "D_DUAL_QUERY_SHA_OR_SOURCE_BINDING")
    reread = query_local(
        core_root, warehouse["dataset_id"], warehouse["version"],
        warehouse["start_ms"], warehouse["end_exclusive_ms"],
        warehouse["decision_cutoff_ms"],
        required_source_sha256=warehouse["source_zip_sha256"],
        require_complete=True)
    require(reread == local_query, "D_CORE_READONLY_QUERY_REPLAY_DRIFT")

    witness = Frozen.restore(core_d_witness_receipt)
    w = witness.data
    require(w.get("schema") == CORE_D_WITNESS_SCHEMA
            and w.get("scope") == "SYNTHETIC_SAME_SOURCE_SOFTWARE_ONLY"
            and w.get("source_kind") == "CORE_ORIGINAL_FORMAT_TEST_ZIP"
            and w.get("source_authority") == "TEST_ONLY_NOT_PUBLISHER_ATTESTED"
            and w.get("historical_pit") == "NOT_ATTESTED"
            and w.get("historical_known_at_ms") is None
            and w.get("research_clock_basis") == "DECLARED_SYNTHETIC_FIXTURE_ONLY"
            and w.get("trading_authority") == "NONE"
            and w.get("dataset_id") == warehouse["dataset_id"]
            and w.get("version") == warehouse["version"]
            and w.get("symbol") == warehouse["symbol"]
            and w.get("source_zip_sha256") == warehouse["source_zip_sha256"]
            and w.get("manifest_integrity_sha256") == warehouse["manifest_integrity_sha256"]
            and w.get("warehouse_receipt_sha256") == warehouse["receipt_sha256"]
            and w.get("core245_price_query_sha256") == native_price_query["price_query_sha256"]
            and w.get("core253_query_local_sha256") == local_query["query_sha256"]
            and w.get("decision_cutoff_ms") == warehouse["decision_cutoff_ms"],
            "D_CORE_D_WITNESS_IDENTITY_OR_SCOPE")
    clocks = w.get("synthetic_available_at_ms_by_bar")
    require(type(clocks) is list and len(clocks) == len(local_query["bars"])
            and 0 < len(clocks) <= 4096,
            "D_TEST_AVAILABILITY_WITNESS_REQUIRED")
    source_id = w.get("scanner_source_id")
    generation_id = w.get("scanner_generation_id")
    require(type(source_id) is str and source_id and type(generation_id) is str
            and generation_id and len(source_id) <= 160 and len(generation_id) <= 160,
            "D_SCANNER_POLICY_SOURCE_LABEL_REQUIRED")
    original_mapping, rows = [], []
    for idx, (bar,clock) in enumerate(zip(local_query["bars"], clocks)):
        require(type(clock) is dict
                and clock.get("bar_open_ms") == bar["bar_open_ms"]
                and clock.get("bar_checksum") == bar["bar_checksum"]
                and type(clock.get("available_at_ms")) is int
                and bar["bar_close_ms"] < clock["available_at_ms"]
                <= warehouse["decision_cutoff_ms"]
                and bar["bar_open_ms"] == warehouse["start_ms"] + idx*WIDTH_MS
                and bar["bar_close_ms"] == bar["bar_open_ms"]+WIDTH_MS-1,
                "D_CORE_D_CLOCK_OR_BAR_CHECKSUM_DRIFT")
        row = {
            "symbol": warehouse["symbol"], "timeframe": "15m",
            "source_id": source_id, "open_ms": bar["bar_open_ms"],
            "close_ms": bar["bar_close_ms"],
            "available_ms": clock["available_at_ms"],
            "finalized": True, "open": bar["open"], "high": bar["high"],
            "low": bar["low"], "close": bar["close"], "volume": bar["volume"],
        }
        rows.append(row)
        original_mapping.append({
            "core_local_bar_checksum": bar["bar_checksum"],
            "core_original_open_ms": bar["bar_open_ms"],
            "scanner_row_sha256": digest(row),
            "synthetic_test_available_ms": clock["available_at_ms"],
            "historical_known_at_ms": None,
        })
    require(len(rows) == warehouse["bar_count"]
            and warehouse["end_exclusive_ms"]
                == warehouse["start_ms"]+len(rows)*WIDTH_MS,
            "D_CORE_D_COMPLETE_SYMBOL_GRID")
    obj = {
        "schema": "aql.strategy-service.synthetic-bars.v1",
        "source_id": source_id, "generation_id": generation_id,
        "rows": rows,
    }
    raw = canonical(obj)
    manifest = {
        "schema": "aql.strategy-service.source.v1",
        "timeframe": "15m", "market": w["scanner_market"],
        "source_id": source_id, "generation_id": generation_id,
        "start_ms": warehouse["start_ms"],
        "end_exclusive_ms": warehouse["end_exclusive_ms"],
        "cutoff_ms": warehouse["decision_cutoff_ms"],
        "evidence_class": "TEST_ONLY",
        "external_verifier": "CORE_D_SYNTHETIC_SOFTWARE_NOT_PIT",
        "raw_sha256": raw_sha(raw),
    }
    members = w.get("research_universe_members")
    require(type(members) is list and 0 < len(members) <= 256
            and len({x["symbol"] for x in members}) == len(members)
            and warehouse["symbol"] in {x["symbol"] for x in members}
            and all(type(x) is dict
                and type(x.get("symbol")) is str and x.get("symbol")
                and x.get("eligible") in (True, False, None)
                and type(x.get("membership_available_ms")) is int
                and 0 <= x["membership_available_ms"] <= warehouse["decision_cutoff_ms"]
                for x in members),
            "D_SOURCE_UNIVERSE_NOT_SYNTHETIC_WITNESSED")
    universe = {
        "schema": "aql.strategy-service.universe.v1",
        "count_unit": "SYMBOL", "cutoff_ms": manifest["cutoff_ms"],
        "evidence_class": "TEST_ONLY",
        "source_raw_sha256": manifest["raw_sha256"],
        "members": members,
    }
    projection = Frozen.build({
        "schema": PROOF_SCHEMA, "core_d_witness_sha256": witness.sha256,
        "core_d_witness_schema": CORE_D_WITNESS_SCHEMA,
        "warehouse_receipt_sha256": warehouse["receipt_sha256"],
        "source_zip_sha256": warehouse["source_zip_sha256"],
        "manifest_integrity_sha256": warehouse["manifest_integrity_sha256"],
        "core245_price_query_sha256": native_price_query["price_query_sha256"],
        "core253_query_local_sha256": local_query["query_sha256"],
        "identity_map_sha256": dual_map["identity_map_sha256"],
        "dataset_id": warehouse["dataset_id"], "source_version": warehouse["version"],
        "symbol": warehouse["symbol"], "timeframe": "15m",
        "cutoff_ms": warehouse["decision_cutoff_ms"],
        "scanner_raw_sha256": raw_sha(raw),
        "scanner_manifest_sha256": digest(manifest),
        "scanner_universe_sha256": digest(universe),
        "source_byte_mapping": original_mapping,
        "core_readonly_query_replay": "VERIFIED_EXACT",
        "source_relationship": "DETERMINISTIC_PROJECTION_FROM_VERIFIED_CORE_QUERY",
        "scientific_same_source_pit": "NOT_ATTESTED",
        "source_authority": "SYNTHETIC_SOFTWARE_ONLY_NOT_ORIGINAL_MARKET",
        "operational_scanner_status": "UNKNOWN",
        "work235_operational_15m": "NOT_CONNECTED_15M_UNSUPPORTED",
        "core_strategy_secretary_state": "NOT_ENQUEUED",
        "factory_lab_activation": "NOT_AUTHORIZED",
        "paper_execution": "NOT_ACTIVATED",
        "trading_authority": "NONE",
    })
    return raw, manifest, universe, projection


def scan_same_core_source(
    core_root, warehouse_receipt, native_price_query_receipt,
    local_query_receipt, dual_identity_map_receipt,
    core_d_research_witness_receipt, work235_specs, *,
    governance_actions, symbol_budget,
):
    """Return canonical Scanner C receipts + extra same-source projection seal.

    The Core D source witness must be issued by Core owner on the exact same
    synthetic research query. This adapter cannot mint a Core-issued witness,
    and this function does not enqueue or approve the Secretary route.
    """
    raw, manifest, universe, projection = _project(
        core_root, warehouse_receipt, native_price_query_receipt,
        local_query_receipt, dual_identity_map_receipt,
        core_d_research_witness_receipt)
    pins = {
        "source_custody_receipt_sha256": warehouse_receipt["receipt_sha256"],
        "core245_price_query_sha256": native_price_query_receipt["price_query_sha256"],
        "core253_query_local_sha256": local_query_receipt["query_sha256"],
        "source_zip_sha256": warehouse_receipt["source_zip_sha256"],
        "source_custody_status": "TEST_ONLY_ATTESTED",
    }
    package = scan_and_prepare_test_only_routes(
        work235_specs, raw, manifest, universe,
        cutoff_ms=manifest["cutoff_ms"], symbol_budget=symbol_budget,
        governance_actions=governance_actions, core_query_pins=pins)
    run = Frozen.restore(package.data["scanner_run"]).data
    require(run["source_status"] == "SYNTHETIC_TEST_ONLY_NATIVE_15M"
            and package.data["total_attempts"]
                == package.data["strategy_count"]*package.data["symbol_denominator"],
            "D_SCANNER_RUN_OR_DENOMINATOR_DRIFT")
    require(all(Frozen.restore(x).data["source_raw_sha256"] == projection.data["scanner_raw_sha256"]
                and Frozen.restore(x).data["source_zip_sha256"] == projection.data["source_zip_sha256"]
                and Frozen.restore(x).data["core245_price_query_sha256"]
                    == projection.data["core245_price_query_sha256"]
                and Frozen.restore(x).data["core253_query_local_sha256"]
                    == projection.data["core253_query_local_sha256"]
                and Frozen.restore(x).data["strategy_secretary_status"] == "NOT_ENQUEUED"
                for x in package.data["strategy_route_requests"]),
            "D_CANONICAL_ROUTE_PROVENANCE_PARENT_DRIFT")
    return Frozen.build({
        "schema": "aql.scanner-d.same-core-source-handoff.v1",
        "research_same_source_projection_receipt": projection.receipt(),
        "scanner_c_canonical_service_receipt": package.receipt(),
        "source_zip_sha256": projection.data["source_zip_sha256"],
        "scanner_raw_sha256": projection.data["scanner_raw_sha256"],
        "distinct_sha_domains_preserved": True,
        "source_binding_status": "CORE_QUERY_TO_SCANNER_BYTES_VERIFIED_SOFTWARE_ONLY",
        "historical_pit": "NOT_ATTESTED",
        "strategy_secretary_status": "NOT_ENQUEUED",
        "operational_paper": "NOT_CONNECTED",
        "trading_authority": "NONE",
        "orders_created": 0, "paper_positions": 0,
        "actual_fills": None,
    })
