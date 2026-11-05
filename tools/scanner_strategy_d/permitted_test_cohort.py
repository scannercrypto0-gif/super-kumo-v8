"""Scanner D TEST_ONLY consumer of the Core D owner-issued permitted AAA cohort.

The single canonical research fixture creator lives in Core D #264:
research_wp_r0.aql_core_d_permitted_cohort_v1.create_permitted_synthetic_cohort.
Scanner D MUST NOT create independent ZIP/CSV or source custody.
"""
from __future__ import annotations

from research_wp_r0.aql_archive_custody_bridge_v1 import digest as core_digest
from research_wp_r0.aql_core_d_permitted_cohort_v1 import create_permitted_synthetic_cohort
from tools.strategy_service_offline.common import Frozen, require
from tools.scanner_strategy_d.core_query_adapter import scan_same_core_source

SOURCE_SYMBOL = "AAA"
COHORT_SCHEMA = "aql.scanner-d.permitted-core-test-cohort.v1"


def create_permitted_core_test_cohort(core_root, vault_root, work235_specs,
                                      governance_actions, *, symbol_budget=1):
    """Consume precisely ONE Core-owner generated synthetic source and receipt.

    This wrapper performs no custody writes of its own; Core D owns its
    deterministic native-format ZIP, immutable RAW Vault and issuer witness.
    """
    core = create_permitted_synthetic_cohort(
        core_root, vault_root, work235_specs, symbol=SOURCE_SYMBOL)
    warehouse, native, local, mapping, witness = (
        core[k] for k in ("warehouse", "native", "local", "mapping", "witness"))
    require(core["receipt"]["schema"]
            == "aql.core.d.permitted-synthetic-cohort.v1"
            and core["receipt"]["cohort_evidence_class"]
            == "SYNTHETIC_TEST_ONLY_NOT_PUBLISHER"
            and core["receipt"]["source_zip_sha256"]
            == warehouse["source_zip_sha256"]
            and core["receipt"]["warehouse_receipt_sha256"]
            == warehouse["receipt_sha256"]
            and core["receipt"]["core_245_price_query_sha256"]
            == native["price_query_sha256"]
            and core["receipt"]["core_253_query_local_sha256"]
            == local["query_sha256"]
            and core["receipt"]["core_d_witness_sha256"]
            == witness["sha256"]
            and core["receipt"]["cohort_sha256"]
            == core_digest({k:v for k,v in core["receipt"].items()
                            if k != "cohort_sha256"}),
            "D_CORE_ISSUED_COHORT_PARENT_DRIFT")
    handoff = scan_same_core_source(
        core_root, warehouse, native, local, mapping, witness,
        work235_specs, governance_actions=governance_actions,
        symbol_budget=symbol_budget)
    service = Frozen.restore(handoff.data["scanner_c_canonical_service_receipt"]).data
    statuses = [x["payload"]["scanner_nomination_status"]
                for x in service["strategy_route_requests"]]
    require(service["total_attempts"] ==
                service["strategy_count"] * service["symbol_denominator"]
            and service["symbol_denominator"] == 1
            and any(x == "SELECTED" for x in statuses)
            and all(x in ("SELECTED", "REJECTED", "UNKNOWN") for x in statuses),
            "D_ALLOWED_CORE_ISSUED_COHORT_HAS_NO_CANDIDATE")
    result = {
        "schema": COHORT_SCHEMA,
        "fixture_origin": "CORE_D_OWNER_TEST_ONLY",
        "core_cohort_receipt": core["receipt"],
        "warehouse": warehouse,
        "native_price_query": native,
        "local_query": local,
        "identity_map": mapping,
        "core_d_issued_witness": witness,
        "scanner_d_handoff": handoff.receipt(),
        "scanner_nomination_statuses": statuses,
        "source_zip_sha256": warehouse["source_zip_sha256"],
        "core_245_price_query_sha256": native["price_query_sha256"],
        "core_253_query_local_sha256": local["query_sha256"],
        "scanner_raw_sha256": handoff.data["scanner_raw_sha256"],
        "historical_known_at_ms": None,
        "historical_pit": "NOT_ATTESTED",
        "strategy_secretary_state": "NOT_ENQUEUED",
        "factory_lab_execution": "NOT_PERFORMED",
        "trading_authority": "NONE",
    }
    return {**result, "cohort_sha256": core_digest(result)}
