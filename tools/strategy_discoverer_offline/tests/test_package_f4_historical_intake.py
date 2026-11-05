"""Package F4 new-seam tests only; E durability tests remain accepted and untouched."""
from dataclasses import replace

import pytest

from tools.strategy_discoverer_offline.contracts import (
    DiscoveryCandidatePackageV1, NominationEvidenceV1,
)
from tools.strategy_discoverer_offline.tests.test_package_e_membership import (
    setup_case, package_fields,
)
from tools.strategy_discoverer_offline.historical_f4_intake import (
    F4RetrospectiveEvidence, F4ResearchIntake, F4ContractError, prepare_f4_intake,
    verify_f4_intake, WAIT, ZERO
)


def case():
    e0,p0,ledger,attempt,head,receipt,log_head=setup_case()
    evidence_dict={**e0._fields_for_digest(), "omission_reason_codes": e0.omission_reason_codes}
    evidence_dict.update(
        evidence_class="RETROSPECTIVE_NON_PIT_VERIFIED",
        source_dataset_id="historical-cohort-2024",
        source_manifest_sha256="a"*64,
        symbol="BTCUSDT",timeframe="15m",
        cutoff_ms=1704070800000,
        independent_verifier_receipt_sha256="b"*64)
    evidence=NominationEvidenceV1.build(**evidence_dict)
    # This fixture's ledger was built against a synthetic evidence digest.
    # It is deliberately insufficient to prove historical membership; F4
    # must stay WAIT even when somebody asserts source/policy flags.
    fields=package_fields(p0)
    fields["nomination_evidence_digest"]=evidence.nomination_digest
    package=DiscoveryCandidatePackageV1.build(**fields)
    cohort=F4RetrospectiveEvidence(
        source_kind="ORIGINAL_PUBLISHER",symbol="BTCUSDT",timeframe="15m",
        market="BINANCE:SPOT:USDT",source_dataset_id="historical-cohort-2024",
        source_manifest_sha256="a"*64,publisher_checksum_sha256=None,
        original_archive_sha256=None,
        core_245_query_sha256=None,core_253_query_sha256=None,
        independent_source_verifier_sha256=None,
        independent_research_policy_approval_sha256=None,
        cutoff_ms=evidence.cutoff_ms,
        first_bar_open_ms=evidence.cutoff_ms-1800000,
        last_bar_open_ms=evidence.cutoff_ms-900000)
    return evidence,package,cohort


def test_missing_genuine_source_policy_outputs_sealed_wait():
    evidence,package,cohort=case()
    intake=prepare_f4_intake(
        package=package,evidence=evidence,cohort=cohort,
        ledger_checkpoint_path="/unavailable/no-such-ledger.sqlite",
        ledger_checkpoint_sha256=None,ledger_attempt_id="not-verified",
        ledger_reference="discoverer-f4")
    assert intake.status == WAIT
    assert intake.evaluation_status=="NOT_EVALUATED"
    assert intake.factory_consumer_status=="NOT_CONNECTED"
    assert intake.holdout_accessed is False
    assert intake.trading_authority=="NONE"
    assert intake.membership_verification_sha256 is None
    assert F4ResearchIntake(**intake.to_dict()) == intake


def test_request_without_source_cannot_be_received_as_factory_admission():
    evidence,package,cohort=case()
    intake=prepare_f4_intake(
        package=package,evidence=evidence,cohort=cohort,
        ledger_checkpoint_path=None,ledger_checkpoint_sha256=None,
        ledger_attempt_id="not-yet-member",ledger_reference="discoverer-f4")
    with pytest.raises(F4ContractError,match="blocked"):
        verify_f4_intake(intake=intake,package=package,evidence=evidence,cohort=cohort,
                         independently_confirm_source=True,
                         independently_confirm_policy=True)


def test_synthetic_evidence_is_forbidden():
    e,p,ledger,attempt,head,receipt,log_head=setup_case()
    _,_,cohort=case()
    with pytest.raises(F4ContractError,match="synthetic evidence"):
        prepare_f4_intake(package=p,evidence=e,cohort=cohort,
                          ledger_checkpoint_path=None,ledger_checkpoint_sha256=None,
                          ledger_attempt_id=attempt,ledger_reference="discoverer-f4")


def test_unknown_evidence_quarantined():
    evidence,package,cohort=case()
    d={**evidence._fields_for_digest(), "omission_reason_codes": evidence.omission_reason_codes}
    d["evidence_class"]="UNKNOWN_UNVERIFIED"
    bad=NominationEvidenceV1.build(**d)
    fields=package_fields(package)
    fields["nomination_evidence_digest"]=bad.nomination_digest
    p2=DiscoveryCandidatePackageV1.build(**fields)
    with pytest.raises(F4ContractError,match="unverified nomination"):
        prepare_f4_intake(package=p2,evidence=bad,cohort=cohort,
                          ledger_checkpoint_path=None,ledger_checkpoint_sha256=None,
                          ledger_attempt_id="bad",ledger_reference="discoverer-f4")


def test_wrong_cutoff_rejected():
    evidence,package,cohort=case()
    d={**evidence._fields_for_digest(), "omission_reason_codes": evidence.omission_reason_codes}
    d["cutoff_ms"]+=900000
    bad=NominationEvidenceV1.build(**d)
    fields=package_fields(package)
    fields["nomination_evidence_digest"]=bad.nomination_digest
    p2=DiscoveryCandidatePackageV1.build(**fields)
    with pytest.raises(F4ContractError,match="source/cutoff/nomination"):
        prepare_f4_intake(package=p2,evidence=bad,cohort=cohort,
                          ledger_checkpoint_path=None,ledger_checkpoint_sha256=None,
                          ledger_attempt_id="bad",ledger_reference="discoverer-f4")


def test_caller_flags_cannot_fake_historical_policy():
    evidence,package,cohort=case()
    with pytest.raises(F4ContractError,match="required"):
        prepare_f4_intake(
            package=package,evidence=evidence,cohort=cohort,
            ledger_checkpoint_path="/unavailable/checkpoint.sqlite",
            ledger_checkpoint_sha256=ZERO,ledger_attempt_id="caller",
            ledger_reference="discoverer-f4",
            source_independently_authenticated=True,
            research_policy_independently_approved=True)


def test_resealed_fake_admission_fails_without_real_parents():
    evidence,package,cohort=case()
    intake=prepare_f4_intake(
        package=package,evidence=evidence,cohort=cohort,
        ledger_checkpoint_path=None,ledger_checkpoint_sha256=None,
        ledger_attempt_id="unknown",ledger_reference="discoverer-f4")
    bad=intake.to_dict()
    bad["status"]="READY_FOR_FACTORY_RESEARCH_INTAKE"
    bad["intake_digest"]="f"*64
    with pytest.raises(F4ContractError):
        F4ResearchIntake(**bad)


def test_reject_future_bar_and_pit_claim():
    evidence,package,cohort=case()
    with pytest.raises(F4ContractError,match="cutoff before last closed"):
        replace(cohort,last_bar_open_ms=cohort.cutoff_ms)
    with pytest.raises(F4ContractError,match="PIT promotion"):
        replace(cohort,historical_pit="PIT_ATTESTED")


def test_missing_or_aliased_core_query_parent_fails():
    evidence,package,cohort=case()
    filled=replace(cohort,
        publisher_checksum_sha256="1"*64,
        original_archive_sha256="2"*64,
        core_245_query_sha256="3"*64,
        core_253_query_sha256="3"*64,
        independent_source_verifier_sha256="4"*64,
        independent_research_policy_approval_sha256="5"*64)
    with pytest.raises(F4ContractError,match="distinct Core"):
        filled.validate_admitted()


def test_mismatched_package_evidence_rejected():
    evidence,package,cohort=case()
    d=package_fields(package)
    d["nomination_evidence_digest"]="e"*64
    tampered=DiscoveryCandidatePackageV1.build(**d)
    with pytest.raises(F4ContractError,match="package/nomination"):
        prepare_f4_intake(package=tampered,evidence=evidence,cohort=cohort,
                          ledger_checkpoint_path=None,ledger_checkpoint_sha256=None,
                          ledger_attempt_id="bad",ledger_reference="discoverer-f4")
