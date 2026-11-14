"""Factory E consumes Discoverer-owned durable SQLite checkpoint by path.

No caller-provided ledger snapshot, self-issued membership proof or unverifiable
Discoverer intake is treated as independent durable custody. This remains
research-only, NOT an actual strategy performance evaluation or historical PIT.
"""
from __future__ import annotations
from research_wp_r0.aql_factory_e_discoverer_consumer_v1 import accept_discoverer_research
from research_wp_r0.aql_factory_e_research_results_store_v1 import ResultsStoreError,digest
from tools.strategy_discoverer_offline.durable_checkpoint_e import DurableDiscovererCheckpoint

def accept_durable_discoverer_e_research(*, discoverer_checkpoint_path,
                                          ledger_checkpoint_sha256,
                                          package,evidence,receipt,intake,
                                          handoff_decision,membership,
                                          experiment_id,store_path,
                                          code_sha256,environment_sha256,
                                          config_sha256,core_source_sha256,
                                          core_245_query_sha256,
                                          core_253_query_sha256):
    # Caller can only identify a pinned independent SQLite checkpoint path,
    # not inject arbitrary ledger rows. This is local durable integrity proof,
    # not remote trust/independent issuer authentication.
    durable=DurableDiscovererCheckpoint(discoverer_checkpoint_path)
    latest=durable.read_latest_ledger()
    if latest["checkpoint_sha"]!=ledger_checkpoint_sha256:
        raise ResultsStoreError("FACTORY_E_DURABLE_CHECKPOINT_PIN_DRIFT")
    actual=durable.verify_membership(
        package=package,ledger_attempt_id=intake.ledger_attempt_id,
        ledger_head_digest=intake.ledger_head_digest,
        ledger_reference=intake.ledger_reference)
    if actual!=membership:
        raise ResultsStoreError("FACTORY_E_DURABLE_MEMBERSHIP_DRIFT")
    result=accept_discoverer_research(
        trusted_ledger_snapshot=latest["entries"],
        package=package,evidence=evidence,receipt=receipt,
        intake=intake,handoff_decision=handoff_decision,
        membership=membership,experiment_id=experiment_id,
        store_path=store_path,code_sha256=code_sha256,
        environment_sha256=environment_sha256,
        config_sha256=config_sha256,
        core_source_sha256=core_source_sha256,
        core_245_query_sha256=core_245_query_sha256,
        core_253_query_sha256=core_253_query_sha256)
    body=dict(
        schema="aql.factory.e.discoverer-durable-consumer.v1",
        experiment_id=experiment_id,
        factory_intake_receipt_sha256=result["receipt_sha256"],
        discoverer_checkpoint_sha256=ledger_checkpoint_sha256,
        independent_membership_sha256=actual.verification_digest,
        intake_status="RESEARCH_INTAKE_RECORDED_NOT_EVALUATED",
        historical_pit="NOT_ATTESTED",lab="NOT_EVALUATED",
        trading_authority="NONE",paper="NOT_ACTIVATED",
        orders_created=0,positions=0,actual_fills=None)
    return {**body,"receipt_sha256":digest(body)}
