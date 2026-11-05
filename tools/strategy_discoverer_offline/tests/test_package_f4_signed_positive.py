"""F4 v2 *engineering-only* Ed25519 positive/negative tests.

Ephemeral signers in these tests are NOT an independent owner/custodian/policy
authority, and NO real E: source, historical candidate or Factory Lab is used.
"""
from dataclasses import replace
import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from tools.strategy_discoverer_offline.contracts import (
    DiscoveryCandidatePackageV1, _canonical, _digest,
)
from tools.strategy_discoverer_offline.ledger import DiscovererLedger, AttemptState
from tools.strategy_discoverer_offline.durable_checkpoint_e import DurableDiscovererCheckpoint
from tools.strategy_discoverer_offline.tests.test_package_e_membership import package_fields
from tools.strategy_discoverer_offline.tests.test_package_f4_historical_intake import case
from tools.strategy_discoverer_offline.historical_f4_intake import (
    prepare_f4_intake, verify_f4_intake, WAIT,
)
from tools.strategy_discoverer_offline.historical_f4_positive import (
    F4ReadyIntakeV2, F4AuthorityError, READY, ROLES, WITNESS_SCHEMA,
    witness_subjects,
)

NOW = 1780000000000
REPORT = "f" * 64  # synthetic fake F2 pin for contract tests only
REF = "independent-historical-ledger-original-ref"  # deliberately not 'discoverer-f4'


def authenticated_fixture(tmp_path):
    nomination, old_package, cohort = case()
    cohort = replace(
        cohort, publisher_checksum_sha256="1"*64, original_archive_sha256="2"*64,
        core_245_query_sha256="3"*64, core_253_query_sha256="4"*64,
        independent_source_verifier_sha256="5"*64,
        independent_research_policy_approval_sha256="6"*64,
    )
    d = package_fields(old_package)
    d["source_manifest_sha256"] = cohort.source_manifest_sha256
    preliminary = DiscoveryCandidatePackageV1.build(**d)
    ledger = DiscovererLedger()
    attempt = "historic-attempt-v2"
    ledger.register(
        attempt_id=attempt, candidate_id=preliminary.candidate_id,
        family_id=preliminary.family_id,
        strategy_digest=preliminary.strategy_definition_digest,
        search_plan_digest=preliminary.search_plan_digest,
        nomination_digest=nomination.nomination_digest,
    )
    ledger.transition(attempt, AttemptState.PENDING)
    d["attempt_ledger_head"] = ledger.head_digest()
    package = DiscoveryCandidatePackageV1.build(**d)
    ledger.transition(attempt, AttemptState.COMPLETE)
    path = tmp_path / "historical-e.sqlite"
    checkpoint_sha = DurableDiscovererCheckpoint(path).append_ledger(ledger.to_dict_list())
    durable = DurableDiscovererCheckpoint(path)
    membership = durable.verify_membership(
        package=package, ledger_attempt_id=attempt,
        ledger_head_digest=package.attempt_ledger_head, ledger_reference=REF,
    )
    return nomination, package, cohort, path, checkpoint_sha, attempt, membership


def signed_authorities(nomination, package, cohort, checkpoint_sha, attempt, membership):
    subjects = witness_subjects(
        package=package, nomination=nomination, cohort=cohort, report_sha=REPORT,
        checkpoint_sha=checkpoint_sha, membership_sha=membership.verification_digest,
        ledger_reference=REF, attempt_id=attempt,
    )
    roots, witnesses = {}, {}
    for idx, role in enumerate(ROLES):
        private = Ed25519PrivateKey.generate()
        key_id = "ephemeral-CI-key-" + str(idx)
        approver = "ephemeral-CI-approver-" + str(idx)
        roots[role] = dict(
            key_id=key_id, approver_id=approver,
            public_key_hex=private.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw).hex(),
        )
        unsigned = dict(
            schema_version=WITNESS_SCHEMA, role=role, key_id=key_id,
            approver_id=approver, subject_sha256=subjects[role],
            not_before_ms=NOW-100000, expires_at_ms=NOW+100000,
        )
        witnesses[role] = {**unsigned, "signature_hex":private.sign(_canonical(unsigned)).hex()}
    return roots, witnesses


def build_case(tmp_path):
    e, p, c, path, sha, attempt, member = authenticated_fixture(tmp_path)
    roots, witnesses = signed_authorities(e,p,c,sha,attempt,member)
    args = dict(package=p,evidence=e,cohort=c,
        ledger_checkpoint_path=path, ledger_checkpoint_sha256=sha,
        ledger_attempt_id=attempt,ledger_reference=REF)
    accepted = prepare_f4_intake(
        **args, external_witnesses=witnesses, independent_trust_roots=roots,
        trusted_now_ms=NOW, independently_pinned_f2_report_sha256=REPORT,
    )
    receiver = dict(
        intake=accepted, package=p, evidence=e, cohort=c, durable_ledger_path=path,
        independent_trust_roots=roots, trusted_now_ms=NOW,
        independently_pinned_f2_report_sha256=REPORT,
    )
    return args, accepted, receiver, roots, witnesses


def test_engineering_positive_role_signatures_original_ledger_reference_restart(tmp_path):
    args,ready,receiver,roots,witnesses=build_case(tmp_path)
    assert isinstance(ready,F4ReadyIntakeV2) and ready.status == READY
    assert ready.original_ledger_reference == REF
    assert ready.waiting_intake["evaluation_status"] == "NOT_EVALUATED"
    assert ready.waiting_intake["factory_consumer_status"] == "NOT_CONNECTED"
    assert ready.waiting_intake["trading_authority"] == "NONE"
    assert F4ReadyIntakeV2(**ready.to_dict()) == ready
    assert verify_f4_intake(**receiver)
    assert verify_f4_intake(**receiver)  # read-only replay, no writes
    assert not DurableDiscovererCheckpoint(args["ledger_checkpoint_path"]).attempt_events()


def test_legacy_flags_cannot_promote_and_missing_signer_denied(tmp_path):
    args,ready,receiver,roots,witnesses=build_case(tmp_path)
    waiting=prepare_f4_intake(**args)
    assert waiting.status == WAIT
    with pytest.raises(F4AuthorityError,match="independent witness"):
        prepare_f4_intake(**args, external_witnesses=witnesses,
                          independently_pinned_f2_report_sha256=REPORT)
    with pytest.raises(F4AuthorityError,match="independent witness"):
        verify_f4_intake(**{**receiver,"independent_trust_roots":None})


def test_wrong_original_ledger_reference_or_checkpoint_rejected(tmp_path):
    args,ready,receiver,roots,witnesses=build_case(tmp_path)
    with pytest.raises((F4AuthorityError,ValueError),match="witness|subject|membership|reference"):
        verify_f4_intake(**{**receiver,"intake": replace_ready(ready,original_ledger_reference="discoverer-f4")})
    with pytest.raises((F4AuthorityError,ValueError),match="checkpoint"):
        prepare_f4_intake(**{**args,"ledger_checkpoint_sha256":"e"*64},
                          external_witnesses=witnesses,independent_trust_roots=roots,
                          trusted_now_ms=NOW,independently_pinned_f2_report_sha256=REPORT)


def replace_ready(ready,**change):
    fields=ready._payload()
    fields.update(change)
    return F4ReadyIntakeV2(**fields,ready_digest=_digest(fields))


def test_resealed_ready_is_not_external_authority(tmp_path):
    args,ready,receiver,roots,witnesses=build_case(tmp_path)
    forged={role:dict(w) for role,w in witnesses.items()}
    forged["RESEARCH_POLICY_APPROVER"]["subject_sha256"]="a"*64
    wrong=replace_ready(ready,witnesses=forged,witnesses_digest=_digest(forged))
    with pytest.raises(F4AuthorityError,match="subject"):
        verify_f4_intake(**{**receiver,"intake":wrong})


def test_wrong_trust_root_and_expiry_rejected(tmp_path):
    args,ready,receiver,roots,witnesses=build_case(tmp_path)
    swapped={k:dict(v) for k,v in roots.items()}
    swapped["RESEARCH_POLICY_APPROVER"]["public_key_hex"]=roots["SOURCE_CUSTODIAN"]["public_key_hex"]
    with pytest.raises(F4AuthorityError):
        verify_f4_intake(**{**receiver,"independent_trust_roots":swapped})
    with pytest.raises(F4AuthorityError,match="time validity"):
        verify_f4_intake(**{**receiver,"trusted_now_ms":NOW+100000})


def test_independent_f2_and_nomination_or_strategy_drift_denied(tmp_path):
    args,ready,receiver,roots,witnesses=build_case(tmp_path)
    with pytest.raises(F4AuthorityError,match="F2 pin"):
        verify_f4_intake(**{**receiver,"independently_pinned_f2_report_sha256":"e"*64})
    with pytest.raises((F4AuthorityError,ValueError)):
        verify_f4_intake(**{**receiver,"cohort":replace(receiver["cohort"],core_253_query_sha256="8"*64)})
    changed=package_fields(receiver["package"])
    changed["strategy_definition_digest"]="9"*64
    package=DiscoveryCandidatePackageV1.build(**changed)
    with pytest.raises((F4AuthorityError,ValueError)):
        verify_f4_intake(**{**receiver,"package":package})


def test_no_positive_without_full_external_approval_even_when_self_flags_true(tmp_path):
    args,ready,receiver,roots,witnesses=build_case(tmp_path)
    fake={role:dict(w) for role,w in witnesses.items()}
    fake["LEDGER_CUSTODIAN"]["signature_hex"]="0"*128
    with pytest.raises(F4AuthorityError,match="signature"):
        prepare_f4_intake(**args,external_witnesses=fake,independent_trust_roots=roots,
                          trusted_now_ms=NOW,independently_pinned_f2_report_sha256=REPORT,
                          source_independently_authenticated=True,
                          research_policy_independently_approved=True)
