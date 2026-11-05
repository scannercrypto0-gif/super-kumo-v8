"""Package E focused regression: verified ledger prefix, attempt association and intake."""
from dataclasses import replace

PROTECTED = {"evaluation_status", "scientific_acceptance", "execution_status", "publishable", "delivery_authorized", "holdout_status", "factory_routing"}


def package_fields(package):
    return {k: v for k, v in package._fields_for_digest().items() if k not in PROTECTED}


import pytest

from tools.strategy_discoverer_offline.contracts import DiscoveryCandidatePackageV1
from tools.strategy_discoverer_offline.ledger import DiscovererLedger, AttemptState
from tools.strategy_discoverer_offline.ledger_membership_verifier import verify_ledger_membership
from tools.strategy_discoverer_offline.research_handoff_e import VerifiedResearchHandoff
from tools.strategy_discoverer_offline.factory_lab_bridge import DiscovererToFactoryBridge
from tools.strategy_discoverer_offline.tests.test_factory_lab_bridge import (
    _make_evidence, _make_package,
)


def setup_case():
    evidence = _make_evidence()
    preliminary = _make_package(evidence)
    ledger = DiscovererLedger()
    attempt_id = "attempt-e-001"
    ledger.register(
        attempt_id=attempt_id, candidate_id=preliminary.candidate_id,
        family_id=preliminary.family_id,
        strategy_digest=preliminary.strategy_definition_digest,
        search_plan_digest=preliminary.search_plan_digest,
        nomination_digest=evidence.nomination_digest,
    )
    ledger.transition(attempt_id, AttemptState.PENDING)
    checkpoint = ledger.head_digest()
    fields = package_fields(preliminary)
    fields["attempt_ledger_head"] = checkpoint
    package = DiscoveryCandidatePackageV1.build(**fields)
    ledger.transition(attempt_id, AttemptState.COMPLETE)
    bridge = DiscovererToFactoryBridge(ledger_reference="e-ledger")
    result = bridge.route(
        package=package, evidence=evidence, ledger_attempt_id=attempt_id,
        ledger_head_digest=checkpoint,
    )
    assert result.routed
    return evidence, package, ledger, attempt_id, checkpoint, result.receipt, bridge.log.head_digest


def admission(case=None):
    e, p, ledger, attempt, checkpoint, receipt, log_head = case or setup_case()
    handoff = VerifiedResearchHandoff("e-ledger")
    decision, intake, membership = handoff.handoff(
        package=p, evidence=e, receipt=receipt,
        entries_data=ledger.to_dict_list(), ledger_attempt_id=attempt,
        ledger_head_digest=checkpoint, attempt_log_head_digest=log_head,
    )
    return handoff, decision, intake, membership


def test_valid_membership_and_admission():
    case = setup_case()
    h, d, intake, proof = admission(case)
    assert d.status == "ELIGIBLE_FOR_FACTORY_RESEARCH"
    assert proof.checkpoint_head == case[4]
    assert proof.entry_digest == case[4]
    assert intake.ledger_membership_status == "NOT_VERIFIED"  # legacy contract cannot self-promote
    assert intake.evaluation_status == "NOT_EVALUATED"
    assert intake.factory_consumer_connected == "FACTORY_CONSUMER_NOT_CONNECTED"
    assert not intake.holdout_accessed
    assert len(h.decisions()) == 1


def test_wrong_attempt_denied():
    e, p, ledger, attempt, head, receipt, log_head = setup_case()
    h = VerifiedResearchHandoff("e-ledger")
    d, intake, membership = h.handoff(
        package=p, evidence=e, receipt=receipt,
        entries_data=ledger.to_dict_list(), ledger_attempt_id="fake",
        ledger_head_digest=head, attempt_log_head_digest=log_head,
    )
    assert d.status == "REJECTED_OR_QUARANTINED_NOT_VERIFIED"
    assert intake is None and membership is None


def test_tampered_chain_denied():
    e, p, ledger, attempt, head, receipt, log_head = setup_case()
    rows = ledger.to_dict_list()
    rows[0]["reason"] = "tampered"
    h = VerifiedResearchHandoff("e-ledger")
    d, intake, membership = h.handoff(
        package=p, evidence=e, receipt=receipt,
        entries_data=rows, ledger_attempt_id=attempt,
        ledger_head_digest=head, attempt_log_head_digest=log_head,
    )
    assert d.status == "REJECTED_OR_QUARANTINED_NOT_VERIFIED"
    assert intake is None


def test_swapped_candidate_identity_denied():
    e, p, ledger, attempt, head, receipt, log_head = setup_case()
    fields = package_fields(p)
    fields["candidate_id"] = "swapped"
    swapped = DiscoveryCandidatePackageV1.build(**fields)
    with pytest.raises(ValueError, match="candidate binding mismatch"):
        verify_ledger_membership(
            entries_data=ledger.to_dict_list(), package=swapped,
            ledger_attempt_id=attempt, ledger_head_digest=head,
            ledger_reference="e-ledger",
        )


def test_missing_checkpoint_denied():
    e, p, ledger, attempt, head, receipt, log_head = setup_case()
    with pytest.raises(ValueError, match="checkpoint absent"):
        verify_ledger_membership(
            entries_data=ledger.to_dict_list()[:1], package=p,
            ledger_attempt_id=attempt, ledger_head_digest=head,
            ledger_reference="e-ledger",
        )


def test_duplicate_attempt_audited():
    e, p, ledger, attempt, head, receipt, log_head = setup_case()
    h = VerifiedResearchHandoff("e-ledger")
    args = dict(package=p, evidence=e, receipt=receipt, entries_data=ledger.to_dict_list(),
                ledger_attempt_id=attempt, ledger_head_digest=head,
                attempt_log_head_digest=log_head)
    d1, _, _ = h.handoff(**args)
    d2, intake2, _ = h.handoff(**args)
    assert d1.status == "ELIGIBLE_FOR_FACTORY_RESEARCH"
    assert d2.status == "REJECTED_OR_QUARANTINED_NOT_VERIFIED"
    assert intake2 is None
    assert len(h.decisions()) == 2


def test_quarantined_receipt_denied():
    e, p, ledger, attempt, head, receipt, log_head = setup_case()
    e2 = _make_evidence(source_availability="UNKNOWN")
    bridge = DiscovererToFactoryBridge(ledger_reference="e-ledger")
    fields = package_fields(p)
    fields["nomination_evidence_digest"] = e2.nomination_digest
    p2 = DiscoveryCandidatePackageV1.build(**fields)
    r = bridge.route(package=p2, evidence=e2,
                     ledger_attempt_id=attempt, ledger_head_digest=head)
    assert not r.routed
    d, intake, membership = VerifiedResearchHandoff("e-ledger").handoff(
        package=p2, evidence=e2, receipt=r.receipt,
        entries_data=ledger.to_dict_list(), ledger_attempt_id=attempt,
        ledger_head_digest=head, attempt_log_head_digest=bridge.log.head_digest,
    )
    assert d.status == "REJECTED_OR_QUARANTINED_NOT_VERIFIED"
    assert intake is None


def test_replay_membership_deterministic():
    e, p, ledger, attempt, head, receipt, log_head = setup_case()
    fields = dict(entries_data=ledger.to_dict_list(), package=p,
                  ledger_attempt_id=attempt, ledger_head_digest=head,
                  ledger_reference="e-ledger")
    a = verify_ledger_membership(**fields)
    b = verify_ledger_membership(**fields)
    assert a.verification_digest == b.verification_digest
    assert ledger.verify_chain()


def test_wrong_head_denied():
    e, p, ledger, attempt, head, receipt, log_head = setup_case()
    with pytest.raises(ValueError, match="checkpoint mismatch"):
        verify_ledger_membership(
            entries_data=ledger.to_dict_list(), package=p,
            ledger_attempt_id=attempt, ledger_head_digest=ledger.head_digest(),
            ledger_reference="e-ledger",
        )


def test_wrong_strategy_binding_denied():
    e, p, ledger, attempt, head, receipt, log_head = setup_case()
    fields = package_fields(p)
    fields["strategy_definition_digest"] = "f" * 64
    mutated = DiscoveryCandidatePackageV1.build(**fields)
    with pytest.raises(ValueError, match="candidate binding mismatch"):
        verify_ledger_membership(
            entries_data=ledger.to_dict_list(), package=mutated,
            ledger_attempt_id=attempt, ledger_head_digest=head,
            ledger_reference="e-ledger",
        )
