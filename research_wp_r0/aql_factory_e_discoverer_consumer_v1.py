"""Factory-owned verified Discoverer E intake, isolated from Scanner's route.

A Discoverer-provided digest or proof is never accepted by itself: Factory
replays the independent trusted ledger checkpoint and verifies the package,
receipt and nomination identities. This is a TEST_ONLY research admission,
NOT a historical strategy backtest, performance score or operational ACK.
"""
from __future__ import annotations

from dataclasses import asdict
from tools.strategy_discoverer_offline.contracts import _digest
from tools.strategy_discoverer_offline.ledger_membership_verifier import verify_ledger_membership
from tools.strategy_discoverer_offline.factory_lab_consumer_contract import (
    DiscovererResearchIntakeV1,
)
from research_wp_r0.aql_factory_e_research_results_store_v1 import (
    build_experiment, register_experiment, ResultsStoreError,
)

SCHEMA = "aql.factory.e.discoverer-verified-consumer.v1"


def accept_discoverer_research(*, trusted_ledger_snapshot, package, evidence,
                               receipt, intake, handoff_decision,
                               membership, experiment_id, store_path,
                               code_sha256, environment_sha256,
                               config_sha256, core_source_sha256,
                               core_245_query_sha256, core_253_query_sha256):
    """Reverify trusted ledger snapshot, then record a research-only admission.

    Snapshot must be loaded by Factory from independent custody, not taken
    from a caller's unsigned membership object. The snapshot itself has no
    external authenticity proof: this function verifies integrity and identity,
    not issuer custody or durability of the in-memory Discoverer ledger.
    """
    if not isinstance(intake, DiscovererResearchIntakeV1):
        raise ResultsStoreError("FACTORY_E_DISCOVERER_INTAKE_TYPE")
    if (handoff_decision.status != "ELIGIBLE_FOR_FACTORY_RESEARCH"
        or handoff_decision.package_digest != package.package_digest
        or handoff_decision.candidate_id != package.candidate_id
        or handoff_decision.intake_digest != intake.intake_digest
        or handoff_decision.membership_verification_digest != membership.verification_digest
        or handoff_decision.decision_digest != _digest({
            "status":handoff_decision.status,
            "candidate_id":handoff_decision.candidate_id,
            "package_digest":handoff_decision.package_digest,
            "intake_digest":handoff_decision.intake_digest,
            "membership_verification_digest":handoff_decision.membership_verification_digest,
            "reason":handoff_decision.reason,
        })):
        raise ResultsStoreError("FACTORY_E_DISCOVERER_HANDOFF_TAMPER")
    verified = verify_ledger_membership(
        entries_data=trusted_ledger_snapshot, package=package,
        ledger_attempt_id=intake.ledger_attempt_id,
        ledger_head_digest=intake.ledger_head_digest,
        ledger_reference=intake.ledger_reference)
    if (verified != membership
        or receipt.routing_status != "ROUTED_SYNTHETIC_ONLY"
        or receipt.package_digest != package.package_digest
        or receipt.receipt_digest != intake.receipt_digest
        or receipt.candidate_id != package.candidate_id
        or receipt.family_id != package.family_id
        or receipt.strategy_definition_digest != package.strategy_definition_digest
        or receipt.nomination_evidence_digest != evidence.nomination_digest
        or receipt.ledger_head_digest != intake.ledger_head_digest
        or receipt.ledger_attempt_id != intake.ledger_attempt_id
        or package.nomination_evidence_digest != evidence.nomination_digest
        or intake.package_digest != package.package_digest
        or intake.candidate_id != package.candidate_id
        or intake.strategy_definition_digest != package.strategy_definition_digest
        or intake.nomination_evidence_digest != evidence.nomination_digest
        or intake.family_id != package.family_id
        or intake.ledger_membership_status != "NOT_VERIFIED"
        or intake.membership_proof_digest is not None
        or intake.factory_consumer_connected != "FACTORY_CONSUMER_NOT_CONNECTED"
        or intake.evaluation_status != "NOT_EVALUATED"
        or intake.holdout_accessed is not False
        or intake.real_execution_initiated is not False
        or intake.work_module_imported is not False):
        raise ResultsStoreError("FACTORY_E_DISCOVERER_INDEPENDENT_IDENTITY")
    attempt = dict(attempt_id=intake.ledger_attempt_id,
                   candidate_id=package.candidate_id, state="SELECTED",
                   source_receipt_sha256=intake.receipt_digest)
    experiment = build_experiment(
        experiment_id=experiment_id, lane="DISCOVERER",
        source_status="SYNTHETIC_ENGINEERING_PASS",
        source_sha256=core_source_sha256,
        source_query_245_sha256=core_245_query_sha256,
        source_query_253_sha256=core_253_query_sha256,
        strategy_definition_sha256=package.strategy_definition_digest,
        config_sha256=config_sha256, code_sha256=code_sha256,
        environment_sha256=environment_sha256,
        parent_receipt_sha256=intake.intake_digest,
        attempts=[attempt],
        lab_receipt_sha256=None, paper_receipt_sha256=None,
        result_sha256=None, evidence_class="TEST_ONLY")
    stored = register_experiment(store_path, experiment)
    fields = dict(schema=SCHEMA, status="RESEARCH_INTAKE_RECORDED_NOT_EVALUATED",
                  experiment_id=experiment_id,
                  experiment_sha256=experiment["sha256"],
                  stored_experiment_sha256=experiment["sha256"],
                  candidate_id=package.candidate_id,
                  package_digest=package.package_digest,
                  intake_digest=intake.intake_digest,
                  independent_membership_sha256=verified.verification_digest,
                  source_class="SYNTHETIC_TEST_ONLY",
                  historical_pit="NOT_ATTESTED",
                  factory_lab_evaluation="NOT_EVALUATED",
                  paper="NOT_ACTIVATED",
                  orders_created=0, positions=0, actual_fills=None,
                  trading_authority="NONE")
    return {**fields, "receipt_sha256": _digest(fields)}
