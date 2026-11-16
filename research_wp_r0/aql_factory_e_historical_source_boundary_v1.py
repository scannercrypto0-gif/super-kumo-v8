"""Factory E historical source admission: genuine missing original stays blocked.

Consumes the Core E signed preflight receipt. A source-verified custody-only
receipt cannot itself authorize PIT, historical strategy approval, or Lab.
"""
from __future__ import annotations

from research_wp_r0.aql_factory_e_research_results_store_v1 import (
    build_experiment, register_experiment, ResultsStoreError, digest,
)


def record_core_e_historical_boundary(*, preflight_receipt, store_path,
                                      experiment_id, code_sha256,
                                      environment_sha256):
    from research_wp_r0.aql_core_e_historical_boundary_v1 import (
        verify_preflight_receipt, BLOCKED, VERIFIED,
    )
    try:
        verified = verify_preflight_receipt(preflight_receipt)
    except (AttributeError, KeyError, TypeError, ValueError):
        verified = False
    if not verified:
        raise ResultsStoreError("FACTORY_E_CORE_E_PREFLIGHT_TAMPER")
    if preflight_receipt["source_kind"] != "ORIGINAL_PUBLISHER":
        raise ResultsStoreError("FACTORY_E_SYNTHETIC_NOT_HISTORICAL")
    # Even a matching local ZIP/checksum only proves custody bytes. The
    # historical query, Scanner historical approval and PIT remain absent.
    if preflight_receipt["status"] not in (BLOCKED, VERIFIED):
        raise ResultsStoreError("FACTORY_E_PREFLIGHT_STATUS")
    if preflight_receipt["historical_pit"] != "NOT_ATTESTED":
        raise ResultsStoreError("FACTORY_E_PIT_PROMOTION")
    status = "HISTORICAL_SOURCE_BLOCKED"
    attempt = dict(
        attempt_id="source-preflight",
        candidate_id=preflight_receipt["dataset_id"],
        state="UNKNOWN",
        source_receipt_sha256=preflight_receipt["receipt_sha256"],
    )
    record = build_experiment(
        experiment_id=experiment_id, lane="HISTORICAL_SOURCE",
        source_status=status,
        source_sha256=preflight_receipt["source_sha256"],
        source_query_245_sha256=None, source_query_253_sha256=None,
        strategy_definition_sha256=None, config_sha256=None,
        code_sha256=code_sha256,
        environment_sha256=environment_sha256,
        parent_receipt_sha256=preflight_receipt["receipt_sha256"],
        attempts=[attempt],
        lab_receipt_sha256=None, paper_receipt_sha256=None,
        result_sha256=None, evidence_class="RETROSPECTIVE_NON_PIT")
    stored = register_experiment(store_path, record)
    body = dict(
        schema="aql.factory.e.historical-source-blocker.v1",
        experiment_id=experiment_id,
        experiment_sha256=record["sha256"],
        preflight_receipt_sha256=preflight_receipt["receipt_sha256"],
        original_bytes_status=preflight_receipt["status"],
        historical_source="HISTORICAL_SOURCE_BLOCKED",
        scanner_historical_strategy="NOT_APPROVED",
        secretary="NOT_ENQUEUED",
        factory_lab="NOT_EXECUTED",
        paper="NOT_ACTIVATED",
        historical_pit="NOT_ATTESTED",
        trading_authority="NONE",
        orders_created=0, paper_positions=0, actual_fills=None,
    )
    return {**body, "receipt_sha256": digest(body)}
